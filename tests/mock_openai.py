"""A local stand-in for the OpenAI Images API, for tests and manual runs.

    python tests/mock_openai.py [--port 8765]

Then set the plugin's API base URL to http://127.0.0.1:8765/v1 and any API
key except `bad-key`. Prompts can steer the response:

- contains `trigger-400` / `trigger-429` / `trigger-500`: that HTTP error
- contains `trigger-stream-error`: an error event in the middle of a stream
- contains `trigger-slow`: waits 30 seconds before answering
- contains `trigger-url`: returns a `url` instead of `b64_json`

Every request is recorded in `server.requests` as
`{ path, headers, json | fields + files }`.
"""

from __future__ import annotations

import argparse
import base64
import json
import struct
import threading
import time
import zlib
from email.parser import BytesParser
from email.policy import default as default_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def solid_png(red: int, green: int, blue: int, size: int = 64) -> bytes:
    """A valid PNG of one color, so previews render in a real View."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    row = b"\x00" + bytes((red, green, blue)) * size
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    signature = b"\x89PNG\r\n\x1a\n"
    return signature + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(row * size)) + chunk(b"IEND", b"")


# The final image and the two previews differ so tests can tell them apart.
FINAL_PNG = solid_png(46, 125, 230)
PARTIAL_PNGS = [solid_png(200, 200, 200), solid_png(120, 160, 220)]
USAGE = {
    "input_tokens": 50,
    "input_tokens_details": {"text_tokens": 40, "image_tokens": 10},
    "output_tokens": 4160,
    "total_tokens": 4210,
}


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class MockHandler(BaseHTTPRequestHandler):
    server: "MockServer"
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - signature of the base class
        if self.server.verbose:
            super().log_message(format, *args)

    # ── helpers ──────────────────────────────────────────────────────────

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: int, message: str, code: str) -> None:
        self.send_json(status, {"error": {"message": message, "type": "invalid_request_error", "code": code}})

    def start_stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def send_event(self, event: str, data: dict[str, Any]) -> None:
        self.wfile.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8"))
        self.wfile.flush()

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def parse_multipart(self, body: bytes) -> tuple[dict[str, str], list[dict[str, Any]]]:
        head = f"Content-Type: {self.headers.get('Content-Type')}\r\n\r\n".encode("utf-8")
        message = BytesParser(policy=default_policy).parsebytes(head + body)
        fields: dict[str, str] = {}
        files: list[dict[str, Any]] = []
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if filename:
                files.append({"field": name, "filename": filename, "contentType": part.get_content_type(), "size": len(payload)})
            else:
                fields[name] = payload.decode("utf-8")
        return fields, files

    # ── routes ───────────────────────────────────────────────────────────

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        if self.path.startswith("/files/"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(FINAL_PNG)))
            self.end_headers()
            self.wfile.write(FINAL_PNG)
            return
        self.send_error_json(404, f"Unknown path {self.path}", "not_found")

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        body = self.read_body()
        record: dict[str, Any] = {"path": self.path, "headers": {key.lower(): value for key, value in self.headers.items()}}
        kind = None
        if self.path.endswith("/images/generations"):
            kind = "image_generation"
            try:
                params = json.loads(body.decode("utf-8"))
            except ValueError:
                self.server.record(record)
                self.send_error_json(400, "Body is not JSON", "invalid_json")
                return
            record["json"] = params
        elif self.path.endswith("/images/edits"):
            kind = "image_edit"
            fields, files = self.parse_multipart(body)
            record["fields"] = fields
            record["files"] = files
            params = dict(fields)
            params["stream"] = fields.get("stream") == "true"
            params["n"] = int(fields.get("n") or 1)
            params["partial_images"] = int(fields.get("partial_images") or 0)
        else:
            self.server.record(record)
            self.send_error_json(404, f"Unknown path {self.path}", "not_found")
            return
        self.server.record(record)

        if self.headers.get("Authorization") == "Bearer bad-key":
            self.send_error_json(401, "Incorrect API key provided: bad-key.", "invalid_api_key")
            return
        prompt = str(params.get("prompt") or "")
        for status in (400, 429, 500):
            if f"trigger-{status}" in prompt:
                self.send_error_json(status, f"Mock error {status} for this prompt.", f"mock_{status}")
                return
        if not prompt:
            self.send_error_json(400, "prompt is required", "missing_prompt")
            return
        if "trigger-slow" in prompt:
            time.sleep(30)

        meta = {
            "size": params.get("size") if params.get("size") not in (None, "auto") else "1024x1024",
            "quality": params.get("quality") if params.get("quality") not in (None, "auto") else "high",
            "background": params.get("background") if params.get("background") not in (None, "auto") else "opaque",
            "output_format": params.get("output_format") or "png",
        }
        n = int(params.get("n") or 1)
        if params.get("stream"):
            self.stream(kind, meta, int(params.get("partial_images") or 0), "trigger-stream-error" in prompt)
            return
        if "trigger-url" in prompt:
            host = self.headers.get("Host")
            data = [{"url": f"http://{host}/files/{index}.png"} for index in range(n)]
        else:
            data = [{"b64_json": b64(FINAL_PNG), "revised_prompt": f"A detailed rendering of: {prompt}"} for _ in range(n)]
        self.send_json(200, {"created": int(time.time()), "data": data, "usage": USAGE, **meta})

    def stream(self, kind: str, meta: dict[str, Any], partials: int, fail: bool) -> None:
        self.start_stream()
        for index in range(min(partials, len(PARTIAL_PNGS))):
            self.send_event(f"{kind}.partial_image", {
                "type": f"{kind}.partial_image",
                "b64_json": b64(PARTIAL_PNGS[index]),
                "partial_image_index": index,
                "created_at": int(time.time()),
                **meta,
            })
            if fail:
                self.send_event("error", {"type": "error", "error": {"message": "Mock stream failure.", "code": "mock_stream"}})
                return
        self.send_event(f"{kind}.completed", {
            "type": f"{kind}.completed",
            "b64_json": b64(FINAL_PNG),
            "created_at": int(time.time()),
            "usage": USAGE,
            **meta,
        })


class MockServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int = 0, verbose: bool = False):
        super().__init__(("127.0.0.1", port), MockHandler)
        self.verbose = verbose
        self.requests: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/v1"

    def record(self, request: dict[str, Any]) -> None:
        with self._lock:
            self.requests.append(request)

    def start(self) -> "MockServer":
        self._thread = threading.Thread(target=self.serve_forever, name="mock-openai", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self.shutdown()
        self.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = MockServer(args.port, verbose=True)
    print(f"Mock OpenAI Images API on {server.base_url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
