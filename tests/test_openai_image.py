"""Tests of tools/openai_image.py against tests/mock_openai.py.

    python -m unittest discover -s tests -v

No network access beyond 127.0.0.1 and no real API key are needed.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TOOL = ROOT / "tools" / "openai_image.py"
sys.path.insert(0, str(HERE))

from mock_openai import FINAL_PNG, PARTIAL_PNGS, MockServer  # noqa: E402


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ToolRun:
    def __init__(self, completed: subprocess.CompletedProcess[bytes]):
        self.returncode = completed.returncode
        self.stdout = completed.stdout.decode("utf-8")
        self.stderr = completed.stderr.decode("utf-8")
        lines = [line for line in self.stdout.splitlines() if line.strip().startswith("{")]
        self.result: dict[str, Any] = json.loads(lines[-1]) if lines else {}
        self.events = [
            json.loads(line[len("@locus "):])
            for line in self.stderr.splitlines()
            if line.startswith("@locus ")
        ]

    @property
    def text(self) -> str:
        return self.result.get("text", "")

    @property
    def is_error(self) -> bool:
        return bool(self.result.get("isError"))


class OpenAIImageToolTests(unittest.TestCase):
    server: MockServer

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = MockServer().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def setUp(self) -> None:
        self.server.requests.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "workspace"
        self.data_dir = Path(self.temp.name) / "plugin-data"
        self.workspace.mkdir()
        self.data_dir.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def settings(self, **overrides: Any) -> dict[str, Any]:
        settings = {
            "apiKey": "test-key",
            "baseUrl": self.server.base_url,
            "organization": "",
            "model": "gpt-image-2.6-flare",
            "defaultSize": "auto",
            "defaultQuality": "auto",
            "defaultBackground": "auto",
            "defaultFormat": "png",
            "outputDir": "Locus/generated/images",
            "attachToModel": True,
        }
        settings.update(overrides)
        return settings

    def run_tool(self, command: str, args: dict[str, Any], *, caller: str = "agent",
                 settings: dict[str, Any] | None = None, timeout: float = 60) -> ToolRun:
        payload = {
            "args": args,
            "settings": self.settings() if settings is None else settings,
            "context": {
                "caller": caller,
                "callId": "call123",
                "workspaceRoot": str(self.workspace),
                "checkoutId": "checkout",
                "projectId": "project",
                "sessionId": None,
                "pluginDataDir": str(self.data_dir),
            },
        }
        env = dict(os.environ)
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env.pop(name, None)
        env["NO_PROXY"] = "127.0.0.1,localhost"
        completed = subprocess.run(
            [sys.executable, str(TOOL), command],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            env=env,
        )
        return ToolRun(completed)

    def output_dir(self) -> Path:
        return self.workspace / "Locus" / "generated" / "images"

    def history(self) -> list[dict[str, Any]]:
        path = self.output_dir() / "history.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    # ── generate ─────────────────────────────────────────────────────────

    def test_generate_saves_image_history_and_attaches_it(self) -> None:
        run = self.run_tool("generate", {"prompt": "A red fox in snow", "quality": "high", "size": "1536x1024"})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(run.is_error, run.text)

        request = self.server.requests[-1]
        self.assertEqual(request["path"], "/v1/images/generations")
        self.assertEqual(request["headers"]["authorization"], "Bearer test-key")
        self.assertNotIn("openai-organization", request["headers"])
        body = request["json"]
        self.assertEqual(body["model"], "gpt-image-2.6-flare")
        self.assertEqual(body["size"], "1536x1024")
        self.assertEqual(body["quality"], "high")
        self.assertEqual(body["output_format"], "png")
        self.assertEqual(body["n"], 1)
        self.assertNotIn("stream", body)

        files = run.result["files"]
        self.assertEqual(len(files), 1)
        saved = Path(files[0])
        self.assertEqual(saved.parent, self.output_dir())
        self.assertRegex(saved.name, r"^\d{8}-\d{6}-a-red-fox-in-snow\.png$")
        self.assertEqual(saved.read_bytes(), FINAL_PNG)
        self.assertEqual(run.result["images"], [{"path": str(saved)}])

        self.assertIn("Generated 1 image with gpt-image-2.6-flare (1536x1024, quality high, png)", run.text)
        self.assertIn("Locus/generated/images/", run.text)
        self.assertIn("Revised prompt: A detailed rendering of: A red fox in snow", run.text)
        self.assertIn("Tokens: input 50 (text 40, image 10), output 4160, total 4210", run.text)

        [entry] = self.history()
        self.assertEqual(entry["tool"], "image_generate")
        self.assertEqual(entry["prompt"], "A red fox in snow")
        self.assertEqual(entry["model"], "gpt-image-2.6-flare")
        self.assertEqual(entry["caller"], "agent")
        self.assertEqual(entry["callId"], "call123")
        self.assertEqual(entry["usage"]["total_tokens"], 4210)
        self.assertTrue(entry["path"].startswith("Locus/generated/images/"))
        self.assertEqual(entry["references"], [])
        self.assertEqual(entry["source"], "apiKey")

        self.assertTrue(any(event["type"] == "progress" for event in run.events))

    def test_generate_several_images_with_a_file_name_and_organization(self) -> None:
        run = self.run_tool(
            "generate",
            {"prompt": "Icons", "n": 2, "fileName": "app-icon.png", "outputFormat": "webp", "model": "gpt-image-2"},
            settings=self.settings(organization="org-123"),
        )
        self.assertFalse(run.is_error, run.text)
        names = sorted(Path(path).name for path in run.result["files"])
        self.assertEqual(names, ["app-icon-1.webp", "app-icon-2.webp"])
        request = self.server.requests[-1]
        self.assertEqual(request["headers"]["openai-organization"], "org-123")
        self.assertEqual(request["json"]["model"], "gpt-image-2")
        self.assertEqual(request["json"]["n"], 2)
        self.assertEqual(len(self.history()), 2)

        again = self.run_tool("generate", {"prompt": "Icons", "fileName": "app-icon-1", "outputFormat": "webp"})
        self.assertEqual(Path(again.result["files"][0]).name, "app-icon-1-2.webp")

    def test_attach_to_model_off_returns_paths_only_to_the_agent(self) -> None:
        run = self.run_tool("generate", {"prompt": "A lighthouse"}, settings=self.settings(attachToModel=False))
        self.assertFalse(run.is_error, run.text)
        self.assertEqual(run.result["images"], [])
        self.assertEqual(len(run.result["files"]), 1)
        self.assertIn("Images are not attached", run.text)

        view = self.run_tool("generate", {"prompt": "A lighthouse"}, caller="view",
                             settings=self.settings(attachToModel=False))
        self.assertEqual(len(view.result["images"]), 1)

    def test_views_stream_and_report_partial_images(self) -> None:
        run = self.run_tool("generate", {"prompt": "A city at night"}, caller="view")
        self.assertFalse(run.is_error, run.text)
        body = self.server.requests[-1]["json"]
        self.assertTrue(body["stream"])
        self.assertEqual(body["partial_images"], 2)

        partials = [event["path"] for event in run.events if event["type"] == "partialImage"]
        self.assertEqual(len(partials), 2)
        for path, expected in zip(partials, PARTIAL_PNGS):
            self.assertTrue(Path(path).is_relative_to(self.data_dir / "partial"))
            self.assertEqual(Path(path).read_bytes(), expected)
        self.assertEqual(Path(run.result["files"][0]).read_bytes(), FINAL_PNG)
        [entry] = self.history()
        self.assertEqual(entry["caller"], "view")
        self.assertEqual(entry["usage"]["output_tokens"], 4160)
        self.assertEqual(entry["size"], "1024x1024")

    def test_several_images_do_not_stream(self) -> None:
        run = self.run_tool("generate", {"prompt": "Tiles", "n": 3}, caller="view")
        self.assertFalse(run.is_error, run.text)
        self.assertNotIn("stream", self.server.requests[-1]["json"])
        self.assertEqual(len(run.result["files"]), 3)

    def test_stream_errors_are_reported(self) -> None:
        run = self.run_tool("generate", {"prompt": "trigger-stream-error"}, caller="view")
        self.assertTrue(run.is_error)
        self.assertIn("Mock stream failure.", run.text)
        self.assertFalse((self.output_dir() / "history.jsonl").exists())

    def test_url_results_are_downloaded(self) -> None:
        run = self.run_tool("generate", {"prompt": "trigger-url"})
        self.assertFalse(run.is_error, run.text)
        self.assertEqual(Path(run.result["files"][0]).read_bytes(), FINAL_PNG)

    def test_absolute_output_folder(self) -> None:
        target = Path(self.temp.name) / "elsewhere"
        run = self.run_tool("generate", {"prompt": "Moon"}, settings=self.settings(outputDir=str(target)))
        self.assertFalse(run.is_error, run.text)
        self.assertEqual(Path(run.result["files"][0]).parent, target)
        self.assertTrue((target / "history.jsonl").is_file())

    # ── edit ─────────────────────────────────────────────────────────────

    def write_image(self, name: str) -> Path:
        path = self.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(FINAL_PNG)
        return path

    def test_edit_uploads_several_references_and_a_mask(self) -> None:
        self.write_image("refs/a.png")
        self.write_image("refs/b.png")
        self.write_image("refs/mask.png")
        run = self.run_tool("edit", {
            "prompt": "Combine both into a poster",
            "images": ["refs/a.png", "refs/b.png"],
            "mask": "refs/mask.png",
            "inputFidelity": "high",
            "quality": "medium",
        })
        self.assertFalse(run.is_error, run.text)
        request = self.server.requests[-1]
        self.assertEqual(request["path"], "/v1/images/edits")
        self.assertEqual(request["fields"]["prompt"], "Combine both into a poster")
        self.assertEqual(request["fields"]["model"], "gpt-image-2.6-flare")
        self.assertEqual(request["fields"]["quality"], "medium")
        self.assertEqual(request["fields"]["input_fidelity"], "high")
        self.assertEqual([item["field"] for item in request["files"]], ["image[]", "image[]", "mask"])
        self.assertEqual([item["contentType"] for item in request["files"]], ["image/png"] * 3)
        self.assertIn("Edited 1 image", run.text)
        [entry] = self.history()
        self.assertEqual(entry["tool"], "image_edit")
        self.assertEqual(entry["references"], ["refs/a.png", "refs/b.png"])

    def test_edit_with_one_reference_uses_the_image_field_and_streams_for_views(self) -> None:
        self.write_image("photo.png")
        run = self.run_tool("edit", {"prompt": "Make it watercolor", "images": ["photo.png"]}, caller="view")
        self.assertFalse(run.is_error, run.text)
        request = self.server.requests[-1]
        self.assertEqual([item["field"] for item in request["files"]], ["image"])
        self.assertEqual(request["fields"]["stream"], "true")
        self.assertEqual(len([event for event in run.events if event["type"] == "partialImage"]), 2)

    def test_edit_validates_references(self) -> None:
        missing = self.run_tool("edit", {"prompt": "x", "images": ["nope.png"]})
        self.assertTrue(missing.is_error)
        self.assertIn("Image not found: nope.png", missing.text)
        (self.workspace / "notes.txt").write_text("hi", encoding="utf-8")
        wrong = self.run_tool("edit", {"prompt": "x", "images": ["notes.txt"]})
        self.assertIn("must be png, jpeg or webp", wrong.text)
        self.write_image("a.png")
        (self.workspace / "mask.webp").write_bytes(FINAL_PNG)
        mask = self.run_tool("edit", {"prompt": "x", "images": ["a.png"], "mask": "mask.webp"})
        self.assertIn("mask must be a PNG file", mask.text)
        empty = self.run_tool("edit", {"prompt": "x", "images": []})
        self.assertIn("images needs at least one image path", empty.text)
        self.assertEqual(self.server.requests, [])

    # ── errors ───────────────────────────────────────────────────────────

    def test_missing_key_points_to_the_settings(self) -> None:
        run = self.run_tool("generate", {"prompt": "x"}, settings=self.settings(apiKey=None))
        self.assertTrue(run.is_error)
        self.assertIn("API key is not set", run.text)
        self.assertIn("Settings → Plugins → OpenAI Image", run.text)
        self.assertEqual(self.server.requests, [])

    def test_http_errors_carry_status_and_message(self) -> None:
        unauthorized = self.run_tool("generate", {"prompt": "x"}, settings=self.settings(apiKey="bad-key"))
        self.assertTrue(unauthorized.is_error)
        self.assertIn("OpenAI API error 401 (invalid_api_key): Incorrect API key provided", unauthorized.text)
        self.assertIn("Check the API key", unauthorized.text)
        for status in (400, 429, 500):
            run = self.run_tool("generate", {"prompt": f"trigger-{status}"})
            self.assertTrue(run.is_error)
            self.assertIn(f"OpenAI API error {status} (mock_{status}): Mock error {status}", run.text)
            if status == 429:
                self.assertIn("rate limit", run.text)

    def test_unreachable_server(self) -> None:
        url = f"http://127.0.0.1:{free_port()}/v1"
        run = self.run_tool("generate", {"prompt": "x"}, settings=self.settings(baseUrl=url))
        self.assertTrue(run.is_error)
        self.assertIn(f"Could not reach {url}", run.text)

    def test_argument_validation(self) -> None:
        cases = [
            ({"prompt": "  "}, "prompt is required"),
            ({"prompt": "x", "n": 5}, "n must be an integer between 1 and 4"),
            ({"prompt": "x", "n": True}, "n must be an integer"),
            ({"prompt": "x", "size": "huge"}, "size must be one of"),
            ({"prompt": "x", "quality": "ultra"}, "quality must be one of"),
            ({"prompt": "x", "background": "transparent", "outputFormat": "jpeg"}, "transparent background needs png or webp"),
            ({"prompt": "x", "fileName": "../evil"}, "fileName is a plain name"),
        ]
        for args, message in cases:
            with self.subTest(args=args):
                run = self.run_tool("generate", args)
                self.assertTrue(run.is_error)
                self.assertIn(message, run.text)
        bad_url = self.run_tool("generate", {"prompt": "x"}, settings=self.settings(baseUrl="ftp://example"))
        self.assertIn("must start with http:// or https://", bad_url.text)
        self.assertEqual(self.server.requests, [])

    def test_unknown_command_and_bad_stdin(self) -> None:
        run = self.run_tool("draw", {"prompt": "x"})
        self.assertTrue(run.is_error)
        self.assertIn("Unknown command 'draw'", run.text)
        completed = subprocess.run([sys.executable, str(TOOL), "generate"], input=b"not json", capture_output=True, timeout=30)
        result = ToolRun(completed)
        self.assertTrue(result.is_error)
        self.assertIn("Invalid input", result.text)

    def test_old_previews_are_pruned(self) -> None:
        partial = self.data_dir / "partial"
        partial.mkdir()
        old = partial / "old-0.png"
        old.write_bytes(b"x")
        stale = time.time() - 3 * 24 * 3600
        os.utime(old, (stale, stale))
        fresh = partial / "fresh-0.png"
        fresh.write_bytes(b"x")
        run = self.run_tool("generate", {"prompt": "x"}, caller="view")
        self.assertFalse(run.is_error, run.text)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())

    # ── Codex subscription (recorded only) ───────────────────────────────

    def codex_result(self, name: str = "20261106-120000-a-cat.png", **overrides: Any) -> dict[str, Any]:
        self.output_dir().mkdir(parents=True, exist_ok=True)
        path = self.output_dir() / name
        path.write_bytes(FINAL_PNG)
        result = {
            "images": [{"path": str(path), "mimeType": "image/png"}],
            "size": "1536x1024",
            "quality": "medium",
            "background": "opaque",
            "outputFormat": "png",
            "usage": {"input_tokens": 20, "output_tokens": 1372, "total_tokens": 1392},
            "generationId": "gen_1",
            "durationMs": 23100,
            "quota": {"usedPercent": 3, "windowMinutes": 1440, "resetsAt": 1793000000, "planType": "pro"},
            "edit": False,
            "ignored": [],
        }
        result.update(overrides)
        return result

    def test_codex_result_is_recorded_without_a_key_or_a_request(self) -> None:
        settings = self.settings(apiKey="")
        run = self.run_tool(
            "generate",
            {"prompt": "A cat", "size": "1024x1024", "codexResult": self.codex_result(ignored=["size"])},
            settings=settings,
        )
        self.assertFalse(run.is_error, run.text)
        self.assertEqual(self.server.requests, [])
        saved = self.output_dir() / "20261106-120000-a-cat.png"
        self.assertEqual(run.result["files"], [str(saved)])
        self.assertEqual(run.result["images"], [{"path": str(saved)}])
        self.assertIn("Generated 1 image on the Codex subscription (1536x1024, quality medium, png) in 23.1 s:", run.text)
        self.assertIn("Ignored on the Codex subscription (the subscription picks them itself): size.", run.text)
        self.assertIn("Codex image quota: 3% used of the 24 h window, resets ", run.text)
        self.assertIn("Tokens: input 20, output 1372, total 1392", run.text)
        [entry] = self.history()
        self.assertEqual(entry["source"], "codex")
        self.assertEqual(entry["model"], "codex")
        self.assertEqual(entry["tool"], "image_generate")
        self.assertEqual(entry["prompt"], "A cat")
        self.assertEqual(entry["size"], "1536x1024")
        self.assertEqual(entry["generationId"], "gen_1")
        self.assertEqual(entry["path"], "Locus/generated/images/20261106-120000-a-cat.png")

    def test_codex_edit_records_references_and_respects_attach_to_model(self) -> None:
        reference = self.workspace / "ref.png"
        reference.write_bytes(FINAL_PNG)
        run = self.run_tool(
            "edit",
            {"prompt": "Make it blue", "images": ["ref.png"], "codexResult": self.codex_result("edit.png", edit=True)},
            settings=self.settings(apiKey="", attachToModel=False),
        )
        self.assertFalse(run.is_error, run.text)
        self.assertTrue(run.text.startswith("Edited 1 image on the Codex subscription"))
        self.assertEqual(run.result["images"], [])
        self.assertIn("Images are not attached", run.text)
        [entry] = self.history()
        self.assertEqual(entry["tool"], "image_edit")
        self.assertEqual(entry["references"], ["ref.png"])

    def test_codex_result_must_point_at_a_saved_image(self) -> None:
        missing = self.run_tool(
            "generate",
            {"prompt": "A cat", "codexResult": {"images": [{"path": str(self.workspace / "nope.png")}]}},
            settings=self.settings(apiKey=""),
        )
        self.assertTrue(missing.is_error)
        self.assertIn("was not saved", missing.text)
        empty = self.run_tool("generate", {"prompt": "A cat", "codexResult": {"images": []}}, settings=self.settings(apiKey=""))
        self.assertTrue(empty.is_error)
        self.assertIn("Codex returned no image", empty.text)
        self.assertFalse((self.output_dir() / "history.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
