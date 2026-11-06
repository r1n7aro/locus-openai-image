#!/usr/bin/env python3
"""OpenAI image tools for Locus (`image_generate`, `image_edit`).

Protocol (`locus-json`): stdin is `{ args, settings, context }`; stderr lines
starting with `@locus ` are progress events; the last stdout line is
`{ text, images, files, isError }`. Only the Python standard library is used.

The plugin's TypeScript handler (`client/tools.ts`) starts this process. With
the API key it passes the call through and this script calls the OpenAI
Images API. When the user allowed the Codex subscription, Locus has already
made and saved the image; the handler then passes `codexResult` and this
script only records it in history.jsonl and writes the reply.
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
import mimetypes
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable

VERSION = "0.2.1"
USER_AGENT = f"locus-openai-image/{VERSION}"
REQUEST_TIMEOUT_S = 540
MAX_IMAGES = 4
MAX_EDIT_IMAGES = 16
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
PARTIAL_IMAGES = 2
PARTIAL_MAX_AGE_S = 24 * 3600

QUALITIES = ("auto", "low", "medium", "high", "xhigh", "max")
BACKGROUNDS = ("auto", "opaque", "transparent")
FORMATS = ("png", "jpeg", "webp")
FIXED_SIZES = ("auto", "1024x1024", "1536x1024", "1024x1536")
SIZE_PATTERN = re.compile(r"^[1-9][0-9]{1,4}x[1-9][0-9]{1,4}$")
EXTENSIONS = {"png": "png", "jpeg": "jpg", "webp": "webp"}
UPLOAD_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
SETTINGS_HINT = "Settings → Plugins → OpenAI Image, or the image icon in the chat input"


class ToolError(Exception):
    """A failure reported to the caller as the tool result."""


# ── protocol ────────────────────────────────────────────────────────────


def emit(event: dict[str, Any]) -> None:
    line = "@locus " + json.dumps(event, ensure_ascii=False) + "\n"
    sys.stderr.buffer.write(line.encode("utf-8"))
    sys.stderr.buffer.flush()


def progress(message: str, value: float | None = None) -> None:
    event: dict[str, Any] = {"type": "progress", "message": message}
    if value is not None:
        event["progress"] = max(0.0, min(1.0, value))
    emit(event)


def reply(result: dict[str, Any]) -> None:
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


# ── options ─────────────────────────────────────────────────────────────


class CallContext:
    """What both modes need: the prompt, the caller and where files go."""

    def __init__(self, args: dict[str, Any], settings: dict[str, Any], context: dict[str, Any]):
        self.args = args
        self.settings = settings
        self.context = context
        self.prompt = text_arg(args, "prompt").strip()
        if not self.prompt:
            raise ToolError("prompt is required.")
        self.caller = str(context.get("caller") or "agent")
        self.call_id = str(context.get("callId") or uuid.uuid4().hex)
        root = context.get("workspaceRoot")
        self.workspace_root = Path(root) if root else None
        data_dir = context.get("pluginDataDir")
        self.data_dir = Path(data_dir) if data_dir else None
        self.attach_to_model = settings.get("attachToModel", True) is not False
        self.output_dir = self.resolve(text_arg(settings, "outputDir") or "Locus/generated/images")

    def resolve(self, raw: str) -> Path:
        path = Path(os.path.expandvars(os.path.expanduser(raw.strip())))
        if path.is_absolute():
            return path
        if self.workspace_root is None:
            raise ToolError(f"'{raw}' is relative, but no workspace is open.")
        return self.workspace_root / path

    def display_path(self, path: Path) -> str:
        if self.workspace_root is not None:
            try:
                return path.resolve().relative_to(self.workspace_root.resolve()).as_posix()
            except ValueError:
                pass
        return str(path)

    @property
    def attach(self) -> bool:
        return self.caller != "agent" or self.attach_to_model


class Options(CallContext):
    """A call with the API key against the OpenAI Images API."""

    def __init__(self, args: dict[str, Any], settings: dict[str, Any], context: dict[str, Any]):
        super().__init__(args, settings, context)
        self.model = (text_arg(args, "model") or text_arg(settings, "model") or "gpt-image-2.6-flare").strip()
        self.size = (text_arg(args, "size") or text_arg(settings, "defaultSize") or "auto").strip().lower()
        if self.size not in FIXED_SIZES and not SIZE_PATTERN.match(self.size):
            raise ToolError(f"size must be one of {', '.join(FIXED_SIZES)} or WIDTHxHEIGHT, got '{self.size}'.")
        self.quality = choice(args, settings, "quality", "defaultQuality", QUALITIES, "auto")
        self.background = choice(args, settings, "background", "defaultBackground", BACKGROUNDS, "auto")
        self.output_format = choice(args, settings, "outputFormat", "defaultFormat", FORMATS, "png")
        if self.background == "transparent" and self.output_format == "jpeg":
            raise ToolError("A transparent background needs png or webp output, not jpeg.")
        n = args.get("n", 1)
        if isinstance(n, float) and n.is_integer():
            n = int(n)
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= MAX_IMAGES:
            raise ToolError(f"n must be an integer between 1 and {MAX_IMAGES}.")
        self.n = n
        self.file_name = sanitize_file_name(text_arg(args, "fileName"))
        # Views and the status panel show partial images; the model does not.
        self.stream = self.caller != "agent" and self.n == 1

        self.api_key = text_arg(settings, "apiKey").strip()
        if not self.api_key:
            raise ToolError(f"The OpenAI API key is not set. Enter it in {SETTINGS_HINT}.")
        base_url = (text_arg(settings, "baseUrl") or "https://api.openai.com/v1").strip().rstrip("/")
        if not re.match(r"^https?://", base_url, re.IGNORECASE):
            raise ToolError(f"The API base URL must start with http:// or https://, got '{base_url}'.")
        self.base_url = base_url
        self.organization = text_arg(settings, "organization").strip()

    def headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": USER_AGENT,
            "Accept": "text/event-stream" if self.stream else "application/json",
        }
        if self.organization:
            headers["OpenAI-Organization"] = self.organization
        return headers

    def common_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "model": self.model,
            "prompt": self.prompt,
            "n": self.n,
            "size": self.size,
            "quality": self.quality,
            "background": self.background,
            "output_format": self.output_format,
        }
        if self.stream:
            fields["stream"] = True
            fields["partial_images"] = PARTIAL_IMAGES
        return fields


def text_arg(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ToolError(f"{key} must be a string.")
    return value


def choice(args: dict[str, Any], settings: dict[str, Any], key: str, setting: str, allowed: Iterable[str], fallback: str) -> str:
    value = (text_arg(args, key) or text_arg(settings, setting) or fallback).strip().lower()
    allowed = tuple(allowed)
    if value not in allowed:
        raise ToolError(f"{key} must be one of {', '.join(allowed)}, got '{value}'.")
    return value


def sanitize_file_name(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    if "/" in raw or "\\" in raw or raw in (".", ".."):
        raise ToolError("fileName is a plain name without folders.")
    stem = re.sub(r"\.(png|jpe?g|webp)$", "", raw, flags=re.IGNORECASE)
    stem = re.sub(r'[<>:"|?*\x00-\x1f]', "-", stem).strip(" .")
    if not stem:
        raise ToolError("fileName has no usable characters.")
    return stem[:80]


def prompt_slug(prompt: str) -> str:
    words = re.findall(r"\w+", prompt.lower(), flags=re.UNICODE)
    slug = ""
    for word in words:
        candidate = f"{slug}-{word}" if slug else word
        if len(candidate) > 40:
            break
        slug = candidate
    return slug or "image"


# ── HTTP ────────────────────────────────────────────────────────────────


def open_request(request: urllib.request.Request, base_url: str):
    try:
        return urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S)
    except urllib.error.HTTPError as error:
        raise ToolError(http_error_message(error)) from None
    except urllib.error.URLError as error:
        reason = error.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise ToolError(f"The request to {base_url} timed out.") from None
        raise ToolError(f"Could not reach {base_url}: {reason}") from None
    except (socket.timeout, TimeoutError):
        raise ToolError(f"The request to {base_url} timed out.") from None


def http_error_message(error: urllib.error.HTTPError) -> str:
    try:
        body = error.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - the status code is still useful
        body = ""
    message = ""
    code = ""
    try:
        payload = json.loads(body)
        details = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(details, dict):
            message = str(details.get("message") or "")
            code = str(details.get("code") or details.get("type") or "")
        elif isinstance(details, str):
            message = details
    except ValueError:
        message = body.strip()[:500]
    text = f"OpenAI API error {error.code}"
    if code:
        text += f" ({code})"
    if message:
        text += f": {message}"
    if error.code == 401:
        text += f"\nCheck the API key in {SETTINGS_HINT}."
    elif error.code == 429:
        text += "\nThe account hit a rate limit or ran out of quota; try again later or check billing."
    return text


def multipart(fields: dict[str, Any], files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    boundary = f"----locus{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        if isinstance(value, bool):
            value = "true" if value else "false"
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )
    for name, path in files:
        mime = UPLOAD_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        filename = path.name.replace('"', "_")
        chunks.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {mime}\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def read_events(response) -> Iterable[dict[str, Any]]:
    """Server-sent events of a streaming response, as parsed `data` objects."""
    data_lines: list[str] = []
    for raw in response:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line == "":
            if data_lines:
                yield parse_event_data("\n".join(data_lines))
                data_lines = []
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        yield parse_event_data("\n".join(data_lines))


def parse_event_data(data: str) -> dict[str, Any]:
    if data.strip() == "[DONE]":
        return {"type": "done"}
    try:
        event = json.loads(data)
    except ValueError:
        raise ToolError("The API sent a malformed streaming event.") from None
    if not isinstance(event, dict):
        raise ToolError("The API sent a malformed streaming event.")
    return event


def event_error(event: dict[str, Any]) -> str | None:
    details = event.get("error")
    if event.get("type") == "error" or details:
        if isinstance(details, dict):
            return str(details.get("message") or details.get("code") or "unknown error")
        return str(details or event.get("message") or "unknown error")
    return None


# ── results ─────────────────────────────────────────────────────────────


class Generated:
    def __init__(self, data: bytes, revised_prompt: str | None):
        self.data = data
        self.revised_prompt = revised_prompt


def decode_image(item: dict[str, Any]) -> bytes:
    encoded = item.get("b64_json")
    if isinstance(encoded, str) and encoded:
        try:
            return base64.b64decode(encoded, validate=False)
        except ValueError:
            raise ToolError("The API returned an image that is not valid base64.") from None
    url = item.get("url")
    if isinstance(url, str) and url:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with open_request(request, url) as response:
            return response.read()
    raise ToolError("The API response contains no image data.")


def collect_json(response) -> tuple[list[Generated], dict[str, Any]]:
    body = response.read().decode("utf-8", "replace")
    try:
        payload = json.loads(body)
    except ValueError:
        raise ToolError("The API returned a response that is not JSON.") from None
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        raise ToolError("The API response contains no images.")
    images = [Generated(decode_image(item), item.get("revised_prompt")) for item in items if isinstance(item, dict)]
    return images, payload


def collect_stream(response, options: Options, kind: str) -> tuple[list[Generated], dict[str, Any]]:
    images: list[Generated] = []
    meta: dict[str, Any] = {}
    partial_dir = (options.data_dir or options.output_dir) / "partial"
    prune_partials(partial_dir)
    ext = EXTENSIONS[options.output_format]
    for event in read_events(response):
        error = event_error(event)
        if error:
            raise ToolError(f"OpenAI API error: {error}")
        event_type = str(event.get("type") or "")
        if event_type.endswith(".partial_image"):
            index = int(event.get("partial_image_index") or 0)
            data = decode_image(event)
            partial_dir.mkdir(parents=True, exist_ok=True)
            path = partial_dir / f"{options.call_id}-{index}.{ext}"
            path.write_bytes(data)
            emit({"type": "partialImage", "path": str(path)})
            progress(f"Partial image {index + 1}/{PARTIAL_IMAGES}", 0.2 + 0.6 * (index + 1) / (PARTIAL_IMAGES + 1))
        elif event_type.endswith(".completed"):
            images.append(Generated(decode_image(event), event.get("revised_prompt")))
            for key in ("usage", "size", "quality", "background", "output_format"):
                if key in event:
                    meta[key] = event[key]
        elif event_type == "done":
            break
    if not images:
        raise ToolError(f"The {kind} stream ended without a final image.")
    return images, meta


def prune_partials(directory: Path) -> None:
    """Drops previews of earlier calls; they are only shown while a call runs."""
    if not directory.is_dir():
        return
    cutoff = time.time() - PARTIAL_MAX_AGE_S
    for entry in directory.iterdir():
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            pass


def unique_path(directory: Path, stem: str, ext: str) -> Path:
    candidate = directory / f"{stem}.{ext}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}.{ext}"
        counter += 1
    return candidate


def save_images(options: Options, images: list[Generated]) -> list[Path]:
    try:
        options.output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ToolError(f"Could not create the output folder {options.output_dir}: {error}") from None
    ext = EXTENSIONS[options.output_format]
    if options.file_name:
        stem = options.file_name
    else:
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        stem = f"{stamp}-{prompt_slug(options.prompt)}"
    paths = []
    for index, image in enumerate(images):
        name = stem if len(images) == 1 else f"{stem}-{index + 1}"
        path = unique_path(options.output_dir, name, ext)
        path.write_bytes(image.data)
        paths.append(path)
    return paths


def write_history(call: CallContext, entries: list[dict[str, Any]]) -> None:
    """One line per image in `<outputDir>/history.jsonl`, read by Image Studio."""
    history = call.output_dir / "history.jsonl"
    created = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    lines = []
    for fields in entries:
        entry = {
            "id": uuid.uuid4().hex,
            "createdAt": created,
            "caller": call.caller,
            "callId": call.call_id,
            "prompt": call.prompt,
            **fields,
        }
        lines.append(json.dumps(entry, ensure_ascii=False))
    history.parent.mkdir(parents=True, exist_ok=True)
    with history.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def append_history(options: Options, tool: str, images: list[Generated], paths: list[Path], meta: dict[str, Any],
                   duration_ms: int, references: list[str]) -> None:
    write_history(options, [
        {
            "tool": tool,
            "source": "apiKey",
            "revisedPrompt": image.revised_prompt,
            "model": options.model,
            "size": meta.get("size") or options.size,
            "quality": meta.get("quality") or options.quality,
            "background": meta.get("background") or options.background,
            "outputFormat": meta.get("output_format") or options.output_format,
            "path": options.display_path(path),
            "references": references,
            "usage": meta.get("usage"),
            "durationMs": duration_ms,
        }
        for image, path in zip(images, paths)
    ])


def usage_text(usage: Any) -> str | None:
    if not isinstance(usage, dict):
        return None
    parts = []
    if "input_tokens" in usage:
        details = usage.get("input_tokens_details") or {}
        extra = ""
        if isinstance(details, dict) and details:
            extra = f" (text {details.get('text_tokens', 0)}, image {details.get('image_tokens', 0)})"
        parts.append(f"input {usage['input_tokens']}{extra}")
    if "output_tokens" in usage:
        parts.append(f"output {usage['output_tokens']}")
    if "total_tokens" in usage:
        parts.append(f"total {usage['total_tokens']}")
    return "Tokens: " + ", ".join(parts) if parts else None


def build_result(options: Options, verb: str, images: list[Generated], paths: list[Path], meta: dict[str, Any],
                 duration_ms: int) -> dict[str, Any]:
    shown = [options.display_path(path) for path in paths]
    size = meta.get("size") or options.size
    quality = meta.get("quality") or options.quality
    noun = "image" if len(paths) == 1 else "images"
    lines = [
        f"{verb} {len(paths)} {noun} with {options.model} ({size}, quality {quality}, {options.output_format}) "
        f"in {duration_ms / 1000:.1f} s:"
    ]
    lines += [f"- {path}" for path in shown]
    revised = [image.revised_prompt for image in images if image.revised_prompt]
    if revised:
        lines.append(f"Revised prompt: {revised[0]}")
    usage = usage_text(meta.get("usage"))
    if usage:
        lines.append(usage)
    attach = options.attach
    if not attach:
        lines.append("(Images are not attached; open the files to view them.)")
    return {
        "text": "\n".join(lines),
        "images": [{"path": str(path)} for path in paths] if attach else [],
        "files": [str(path) for path in paths],
        "isError": False,
    }


# ── commands ────────────────────────────────────────────────────────────


def run_request(options: Options, request: urllib.request.Request, kind: str) -> tuple[list[Generated], dict[str, Any]]:
    progress("Sending request" if not options.stream else "Waiting for the first preview", 0.05)
    with open_request(request, options.base_url) as response:
        content_type = response.headers.get("Content-Type", "")
        if options.stream and "text/event-stream" in content_type:
            return collect_stream(response, options, kind)
        return collect_json(response)


def generate(options: Options) -> dict[str, Any]:
    started = time.monotonic()
    body = json.dumps(options.common_fields()).encode("utf-8")
    headers = options.headers()
    headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{options.base_url}/images/generations", data=body, headers=headers, method="POST")
    images, payload = run_request(options, request, "generation")
    progress("Saving", 0.95)
    paths = save_images(options, images)
    duration_ms = int((time.monotonic() - started) * 1000)
    append_history(options, "image_generate", images, paths, payload, duration_ms, [])
    return build_result(options, "Generated", images, paths, payload, duration_ms)


def edit(options: Options) -> dict[str, Any]:
    raw_images = options.args.get("images")
    if isinstance(raw_images, str):
        raw_images = [raw_images]
    if not isinstance(raw_images, list) or not raw_images:
        raise ToolError("images needs at least one image path.")
    if len(raw_images) > MAX_EDIT_IMAGES:
        raise ToolError(f"images takes at most {MAX_EDIT_IMAGES} paths.")
    references = [check_upload(options, raw, "image") for raw in raw_images]
    mask_raw = text_arg(options.args, "mask").strip()
    mask = check_upload(options, mask_raw, "mask") if mask_raw else None
    if mask is not None and mask.suffix.lower() != ".png":
        raise ToolError("mask must be a PNG file.")
    fields = options.common_fields()
    fidelity = text_arg(options.args, "inputFidelity").strip().lower()
    if fidelity:
        if fidelity not in ("high", "low"):
            raise ToolError("inputFidelity must be high or low.")
        fields["input_fidelity"] = fidelity
    field_name = "image" if len(references) == 1 else "image[]"
    files = [(field_name, path) for path in references]
    if mask is not None:
        files.append(("mask", mask))

    started = time.monotonic()
    progress("Uploading references", 0.02)
    body, content_type = multipart(fields, files)
    headers = options.headers()
    headers["Content-Type"] = content_type
    request = urllib.request.Request(f"{options.base_url}/images/edits", data=body, headers=headers, method="POST")
    images, payload = run_request(options, request, "edit")
    progress("Saving", 0.95)
    paths = save_images(options, images)
    duration_ms = int((time.monotonic() - started) * 1000)
    append_history(options, "image_edit", images, paths, payload, duration_ms,
                   [options.display_path(path) for path in references])
    return build_result(options, "Edited", images, paths, payload, duration_ms)


def check_upload(options: Options, raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ToolError(f"Each {label} path must be a non-empty string.")
    path = options.resolve(raw)
    if not path.is_file():
        raise ToolError(f"{label.capitalize()} not found: {raw}")
    if path.suffix.lower() not in UPLOAD_TYPES:
        raise ToolError(f"{label.capitalize()} must be png, jpeg or webp: {raw}")
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        raise ToolError(f"{label.capitalize()} is larger than 50 MiB: {raw}")
    return path


# ── Codex subscription (recorded only) ──────────────────────────────────


CODEX_IGNORED_HINT = "the subscription picks them itself"


def quota_text(quota: Any) -> str | None:
    if not isinstance(quota, dict):
        return None
    used = quota.get("usedPercent")
    if not isinstance(used, (int, float)):
        return None
    text = f"Codex image quota: {used:g}% used"
    window = quota.get("windowMinutes")
    if isinstance(window, (int, float)) and window > 0:
        text += f" of the {window / 60:g} h window"
    resets = quota.get("resetsAt")
    if isinstance(resets, (int, float)) and resets > 0:
        when = _dt.datetime.fromtimestamp(resets).astimezone().isoformat(timespec="minutes")
        text += f", resets {when}"
    return text + "."


def record_codex(tool: str, args: dict[str, Any], settings: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Records an image Locus made on the Codex subscription and builds the reply."""
    call = CallContext(args, settings, context)
    result = args.get("codexResult")
    if not isinstance(result, dict):
        raise ToolError("codexResult must be an object.")
    paths = []
    for item in result.get("images") or []:
        raw = item.get("path") if isinstance(item, dict) else None
        if not isinstance(raw, str) or not raw:
            continue
        path = Path(raw)
        if not path.is_file():
            raise ToolError(f"The Codex image was not saved: {raw}")
        paths.append(path)
    if not paths:
        raise ToolError("Codex returned no image.")
    edit = tool == "image_edit"
    raw_refs = args.get("images") if edit else None
    if isinstance(raw_refs, str):
        raw_refs = [raw_refs]
    references = [call.display_path(call.resolve(raw)) for raw in raw_refs or [] if isinstance(raw, str) and raw.strip()]
    size = str(result.get("size") or "auto")
    quality = str(result.get("quality") or "auto")
    output_format = str(result.get("outputFormat") or Path(paths[0]).suffix.lstrip(".") or "png")
    duration_ms = int(result.get("durationMs") or 0)
    write_history(call, [
        {
            "tool": tool,
            "source": "codex",
            "revisedPrompt": None,
            "model": "codex",
            "size": size,
            "quality": quality,
            "background": result.get("background") or "auto",
            "outputFormat": output_format,
            "path": call.display_path(path),
            "references": references,
            "usage": result.get("usage"),
            "durationMs": duration_ms,
            "generationId": result.get("generationId"),
        }
        for path in paths
    ])
    verb = "Edited" if edit else "Generated"
    noun = "image" if len(paths) == 1 else "images"
    lines = [
        f"{verb} {len(paths)} {noun} on the Codex subscription ({size}, quality {quality}, {output_format}) "
        f"in {duration_ms / 1000:.1f} s:"
    ]
    lines += [f"- {call.display_path(path)}" for path in paths]
    ignored = [str(name) for name in result.get("ignored") or [] if isinstance(name, str)]
    if ignored:
        lines.append(f"Ignored on the Codex subscription ({CODEX_IGNORED_HINT}): {', '.join(ignored)}.")
    usage = usage_text(result.get("usage"))
    if usage:
        lines.append(usage)
    quota = quota_text(result.get("quota"))
    if quota:
        lines.append(quota)
    if not call.attach:
        lines.append("(Images are not attached; open the files to view them.)")
    return {
        "text": "\n".join(lines),
        "images": [{"path": str(path)} for path in paths] if call.attach else [],
        "files": [str(path) for path in paths],
        "isError": False,
    }


COMMANDS: dict[str, Callable[[Options], dict[str, Any]]] = {"generate": generate, "edit": edit}
TOOL_NAMES = {"generate": "image_generate", "edit": "image_edit"}


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    handler = COMMANDS.get(command)
    if handler is None:
        reply({"text": f"Unknown command '{command}'. Use generate or edit.", "isError": True})
        return 0
    try:
        raw = sys.stdin.buffer.read().decode("utf-8-sig")
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ToolError("stdin must be a JSON object.")
        args = payload.get("args") or {}
        if not isinstance(args, dict):
            raise ToolError("args must be an object.")
        settings = payload.get("settings") or {}
        context = payload.get("context") or {}
        if "codexResult" in args:
            reply(record_codex(TOOL_NAMES[command], args, settings, context))
            return 0
        options = Options(args, settings, context)
        reply(handler(options))
    except ToolError as error:
        reply({"text": str(error), "isError": True})
    except ValueError as error:
        reply({"text": f"Invalid input: {error}", "isError": True})
    except OSError as error:
        reply({"text": f"File error: {error}", "isError": True})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
