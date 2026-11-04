# -*- coding: utf-8 -*-
"""MarkItDown-Chinese wrapper test suite.

Run from the repository root:

    python -m unittest discover -s tests -p "test_*.py"

The test module itself only uses the Python standard library. The PNG/PDF/PPTX
fixtures are embedded as base64 so no Pillow/python-pptx import is required.
"""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import markitdown_wrapper as mw  # noqa: E402


MOCK_OTSL = (
    "<table><fcel>姓名<fcel>年龄<fcel>城市<nl>"
    "<fcel>张三<fcel>30<fcel>北京<nl></table>"
)


def fixture(name: str) -> bytes:
    return base64.b64decode(
        {"png": PNG_B64, "pdf": PDF_B64, "pptx": PPTX_B64}[name]
    )


def wav_bytes(frames: int = 1600, rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(b"\x00\x00" * frames)
    return buffer.getvalue()


class MockHandler(BaseHTTPRequestHandler):
    requests = []
    lock = threading.Lock()
    conflict_count = 0

    def log_message(self, *args):  # noqa: D401 - silence test server
        pass

    def _send(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802 - stdlib API
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            payload = {}
        with self.lock:
            self.requests.append({"path": self.path, "payload": payload})

        if self.path.endswith("/chat/completions"):
            body = json.dumps(
                {"choices": [{"message": {"content": MOCK_OTSL}}]},
                ensure_ascii=False,
            ).encode("utf-8")
            self._send(body, "application/json")
            return

        if self.path.endswith("/audio/speech_conflict"):
            type(self).conflict_count += 1
            rate = 16000 if type(self).conflict_count % 2 else 8000
            self._send(wav_bytes(rate=rate), "audio/wav")
            return

        if self.path.endswith("/audio/speech_mp3"):
            self._send(b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 64, "audio/mpeg")
            return

        if self.path.endswith("/audio/speech_json"):
            body = json.dumps(
                {"audio": base64.b64encode(wav_bytes()).decode("ascii")}
            ).encode("utf-8")
            self._send(body, "application/json")
            return

        if self.path.endswith("/audio/speech"):
            self._send(wav_bytes(), "audio/wav")
            return

        self.send_response(404)
        self.end_headers()


class WrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        MockHandler.requests.clear()
        MockHandler.conflict_count = 0

    def tearDown(self):
        self.tmpdir.cleanup()

    def config(self, **overrides):
        config = dict(mw.DEFAULT_CONFIG)
        config.update(
            {
                "enable_ocr": True,
                "enable_ocr_fallback": True,
                "ocr_api_base": self.base,
                "ocr_api_key": "",
                "ocr_model": "Xiaomi-OCR-0",
                "ocr_timeout": 10,
                "ocr_max_tokens": 1024,
                "ocr_dpi": 100,
                "ocr_max_pages": 5,
                "ocr_max_workers": 2,
                "ocr_min_chars": 20,
                "tts_api_base": self.base,
                "tts_api_key": "",
                "tts_model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
                "tts_voice": "vivian",
                "tts_language": "Auto",
                "tts_format": "wav",
                "tts_endpoint": "/audio/speech",
                "tts_timeout": 10,
                "tts_max_chars": 50,
            }
        )
        config.update(overrides)
        return config

    # ------------------------------------------------------------------
    # Version / config
    # ------------------------------------------------------------------

    def test_version_labels(self):
        self.assertEqual(mw.WRAPPER_VERSION, "v0.2.0 (AI Enhanced)")
        readme = (ROOT / "README.md").read_text(encoding="utf-8-sig")
        interactive = (ROOT / "Interactive-MarkItDown.ps1").read_text(
            encoding="utf-8-sig"
        )
        convert = (ROOT / "Convert-MarkItDown.ps1").read_text(encoding="utf-8-sig")
        for text in (readme, interactive, convert):
            self.assertIn("v0.2.0 (AI Enhanced)", text)
        self.assertIn("0.1.7", readme)
        self.assertIn("0.1.7", interactive)
        self.assertIn("0.1.7", convert)

    def test_config_example_tracked_and_ignored(self):
        self.assertTrue((ROOT / "config.example.json").is_file())
        self.assertIn(
            "config.json",
            (ROOT / ".gitignore").read_text(encoding="utf-8"),
        )

    def test_load_config_copies_example(self):
        example = json.loads(
            (ROOT / "config.example.json").read_text(encoding="utf-8")
        )
        (self.tmp / "config.example.json").write_text(
            json.dumps(example, ensure_ascii=False), encoding="utf-8"
        )
        with mock.patch.object(mw, "ROOT", self.tmp):
            config = mw.load_config(self.tmp / "config.json")
        self.assertEqual(config["ocr_api_base"], example["ocr_api_base"])
        self.assertEqual(
            json.loads((self.tmp / "config.json").read_text(encoding="utf-8")),
            example,
        )

    def test_wrapper_cli_autocopies_config(self):
        shutil.copy(ROOT / "markitdown_wrapper.py", self.tmp / "markitdown_wrapper.py")
        shutil.copy(ROOT / "config.example.json", self.tmp / "config.example.json")
        source = self.tmp / "input.md"
        source.write_text("# plain\n", encoding="utf-8")
        output = self.tmp / "output.md"
        proc = subprocess.run(
            [
                sys.executable,
                str(self.tmp / "markitdown_wrapper.py"),
                str(source),
                "-o",
                str(output),
            ],
            cwd=str(self.tmp),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertTrue((self.tmp / "config.json").is_file())

    @unittest.skipUnless(os.name == "nt", "Windows-only PowerShell entry point")
    def test_interactive_autocopies_config(self):
        shutil.copy(
            ROOT / "Interactive-MarkItDown.ps1",
            self.tmp / "Interactive-MarkItDown.ps1",
        )
        shutil.copy(ROOT / "config.example.json", self.tmp / "config.example.json")
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.tmp / "Interactive-MarkItDown.ps1"),
            ],
            cwd=str(self.tmp),
            input="q\r\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        self.assertTrue(
            (self.tmp / "config.json").is_file(),
            proc.stdout[-500:] + proc.stderr[-500:],
        )

    # ------------------------------------------------------------------
    # OTSL
    # ------------------------------------------------------------------

    def test_otsl_basic(self):
        self.assertEqual(
            mw.convert_otsl_to_markdown(MOCK_OTSL),
            "| 姓名 | 年龄 | 城市 |\n"
            "| --- | --- | --- |\n"
            "| 张三 | 30 | 北京 |",
        )

    def test_otsl_merged_cells(self):
        text = "<table><fcel>H<lcel><nl><fcel>A<fcel>B<nl></table>"
        self.assertEqual(
            mw.convert_otsl_to_markdown(text),
            "| H | H |\n| --- | --- |\n| A | B |",
        )

    def test_otsl_up_and_cross(self):
        text = (
            "<table><fcel>A<lcel><lcel><nl>"
            "<fcel>B<ucel><ucel><nl>"
            "<fcel>C<ucel><xcel><nl></table>"
        )
        self.assertEqual(
            mw.convert_otsl_to_markdown(text),
            "| A | A | A |\n"
            "| --- | --- | --- |\n"
            "| B | A | A |\n"
            "| C | A | A |",
        )

    def test_otsl_empty_and_pipe(self):
        text = "<table><fcel>A<ecel><nl><fcel>x|y<fcel>B<nl></table>"
        result = mw.convert_otsl_to_markdown(text)
        self.assertIn("| A |  |", result)
        self.assertIn("x\\|y", result)

    def test_otsl_latex_preserved(self):
        text = r"<table><fcel>$\frac{1}{2}$<fcel>B<nl></table>"
        self.assertIn(r"$\frac{1}{2}$", mw.convert_otsl_to_markdown(text))

    def test_otsl_passthrough(self):
        text = "普通文本\n\n| A | B |\n| --- | --- |\n| 1 | 2 |"
        self.assertEqual(mw.convert_otsl_to_markdown(text), text)

    def test_otsl_multiple_tables(self):
        text = "before\n\n" + MOCK_OTSL + "\n\nafter"
        result = mw.convert_otsl_to_markdown(text)
        self.assertIn("before", result)
        self.assertIn("after", result)
        self.assertEqual(result.count("| --- | --- | --- |"), 1)

    # ------------------------------------------------------------------
    # OCR / llm_client
    # ------------------------------------------------------------------

    def test_llm_client_shape(self):
        client = mw._UrllibOpenAIClient(self.config())
        data_uri = "data:image/png;base64," + base64.b64encode(
            fixture("png")
        ).decode("ascii")
        response = client.chat.completions.create(
            model="Xiaomi-OCR-0",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all information"},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
        )
        content = response.choices[0].message.content
        self.assertIn("姓名", content)
        self.assertNotIn("<fcel>", content)

    def test_convert_native_passes_llm_client(self):
        config = self.config()
        fake_result = SimpleNamespace(markdown="ok")
        with mock.patch("markitdown.MarkItDown") as markitdown_cls:
            markitdown_cls.return_value.convert.return_value = fake_result
            text = mw.convert_native(self.tmp / "dummy.md", config)
        self.assertEqual(text, "ok")
        kwargs = markitdown_cls.call_args.kwargs
        self.assertIsInstance(kwargs["llm_client"], mw._UrllibOpenAIClient)
        self.assertEqual(kwargs["llm_model"], "Xiaomi-OCR-0")
        self.assertIn("Extract all information", kwargs["llm_prompt"])

    def test_image_ocr_returns_markdown_table(self):
        image = self.tmp / "sample.png"
        image.write_bytes(fixture("png"))
        result = mw.convert_file(image, self.config())
        self.assertIn("| 姓名 | 年龄 | 城市 |", result)
        self.assertNotIn("<fcel>", result)

    def test_pdf_ocr_fallback(self):
        pdf = self.tmp / "blank.pdf"
        pdf.write_bytes(fixture("pdf"))
        result = mw.convert_file(pdf, self.config(ocr_min_chars=20))
        self.assertIn("| 姓名 |", result)
        self.assertNotIn("<fcel>", result)

    def test_dead_ocr_falls_back(self):
        image = self.tmp / "sample.png"
        image.write_bytes(fixture("png"))
        config = self.config(
            ocr_api_base="http://127.0.0.1:1/v1",
            ocr_timeout=1,
        )
        result = mw.convert_file(image, config)
        self.assertIsInstance(result, str)

    def test_pptx_embedded_image(self):
        pptx = self.tmp / "embedded.pptx"
        pptx.write_bytes(fixture("pptx"))
        result = mw.convert_file(pptx, self.config())
        self.assertIn("姓名", result)
        self.assertNotIn("<fcel>", result)

    # ------------------------------------------------------------------
    # TTS
    # ------------------------------------------------------------------

    def _tts(self, text: str, endpoint: str = "/audio/speech", name: str = "voice"):
        markdown = self.tmp / f"{name}.md"
        markdown.write_text(text, encoding="utf-8")
        output_dir = self.tmp / "output"
        output_dir.mkdir()
        config = self.config(tts_endpoint=endpoint, tts_max_chars=50)
        with mock.patch.object(mw, "OUTPUT_DIR", output_dir):
            paths = mw.tts_file(markdown, config)
        return paths

    def test_tts_wav_merge(self):
        paths = self._tts(
            "第一段。" * 20 + "\n\n" + "第二段。" * 20,
            name="merge",
        )
        self.assertEqual(len(paths), 1)
        with wave.open(str(paths[0]), "rb") as reader:
            self.assertEqual(reader.getnchannels(), 1)
            self.assertEqual(reader.getsampwidth(), 2)
            self.assertEqual(reader.getframerate(), 16000)
            self.assertGreater(reader.getnframes(), 1600)
            self.assertEqual(reader.getnframes() % 1600, 0)

    def test_tts_conflict_falls_back_to_parts(self):
        paths = self._tts(
            "第一段。" * 30,
            endpoint="/audio/speech_conflict",
            name="conflict",
        )
        self.assertGreater(len(paths), 1)
        self.assertTrue(any("_01" in path.name for path in paths))

    def test_tts_non_wav_falls_back_to_parts(self):
        paths = self._tts(
            "第一段。" * 30,
            endpoint="/audio/speech_mp3",
            name="mp3",
        )
        self.assertGreater(len(paths), 1)

    def test_tts_single_wav(self):
        paths = self._tts("短文本。", name="single")
        self.assertEqual(len(paths), 1)

    def test_tts_json_base64(self):
        paths = self._tts(
            "这是一段测试。",
            endpoint="/audio/speech_json",
            name="json",
        )
        self.assertEqual(len(paths), 1)
        with wave.open(str(paths[0]), "rb") as reader:
            self.assertGreater(reader.getnframes(), 0)

    def test_tts_unconfigured(self):
        markdown = self.tmp / "x.md"
        markdown.write_text("hello", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            mw.tts_file(markdown, self.config(tts_api_base=""))

    # ------------------------------------------------------------------
    # Native conversion
    # ------------------------------------------------------------------

    def test_native_matches_cli(self):
        source = self.tmp / "sample.md"
        source.write_text("# Title\n\nHello **world**.\n", encoding="utf-8")
        cli_output = self.tmp / "cli.md"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "markitdown",
                str(source),
                "-o",
                str(cli_output),
            ],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(
            mw.convert_native(source),
            cli_output.read_text(encoding="utf-8"),
        )


# ----------------------------------------------------------------------
# Binary fixtures (generated once; decoded with the standard library only)
# ----------------------------------------------------------------------

PNG_B64 = """iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFUlEQVR4nGP8//8/AzbAhFV00EoAAFbUAw037MyjAAAAAElFTkSu
QmCC"""

PDF_B64 = """JVBERi0xLjQKJSBjcmVhdGVkIGJ5IFBpbGxvdyBQREYgZHJpdmVyCjQgMCBvYmo8PAovVHlwZSAvQ2F0YWxvZwovUGFnZXMgNSAw
IFIKPj5lbmRvYmoKNSAwIG9iajw8Ci9UeXBlIC9QYWdlcwovQ291bnQgMQovS2lkcyBbIDIgMCBSIF0KPj5lbmRvYmoKMSAwIG9i
ajw8Ci9UeXBlIC9YT2JqZWN0Ci9TdWJ0eXBlIC9JbWFnZQovV2lkdGggNjEyCi9IZWlnaHQgNzkyCi9GaWx0ZXIgL0RDVERlY29k
ZQovQml0c1BlckNvbXBvbmVudCA4Ci9Db2xvclNwYWNlIC9EZXZpY2VSR0IKL0xlbmd0aCA4NDI3Cj4+c3RyZWFtCv/Y/+AAEEpG
SUYAAQEAAAEAAQAA/9sAQwAIBgYHBgUIBwcHCQkICgwUDQwLCwwZEhMPFB0aHx4dGhwcICQuJyAiLCMcHCg3KSwwMTQ0NB8nOT04
MjwuMzQy/9sAQwEJCQkMCwwYDQ0YMiEcITIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy
/8AAEQgDGAJkAwEiAAIRAQMRAf/EAB8AAAEFAQEBAQEBAAAAAAAAAAABAgMEBQYHCAkKC//EALUQAAIBAwMCBAMFBQQEAAABfQEC
AwAEEQUSITFBBhNRYQcicRQygZGhCCNCscEVUtHwJDNicoIJChYXGBkaJSYnKCkqNDU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVm
Z2hpanN0dXZ3eHl6g4SFhoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2drh4uPk5ebn6Onq
8fLz9PX29/j5+v/EAB8BAAMBAQEBAQEBAQEAAAAAAAABAgMEBQYHCAkKC//EALURAAIBAgQEAwQHBQQEAAECdwABAgMRBAUhMQYS
QVEHYXETIjKBCBRCkaGxwQkjM1LwFWJy0QoWJDThJfEXGBkaJicoKSo1Njc4OTpDREVGR0hJSlNUVVZXWFlaY2RlZmdoaWpzdHV2
d3h5eoKDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uLj5OXm5+jp6vLz9PX29/j5
+v/aAAwDAQACEQMRAD8A9/ooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiii
gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo
ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK
KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKA
CiiigAooooAKKKKACiiigD//2QplbmRzdHJlYW0KZW5kb2JqCjIgMCBvYmo8PAovUmVzb3VyY2VzIDw8Ci9Qcm9jU2V0IFsgL1BE
RiAvSW1hZ2VDIF0KL1hPYmplY3QgPDwKL2ltYWdlIDEgMCBSCj4+Cj4+Ci9NZWRpYUJveCBbIDAgMCA2MTIuMCA3OTIuMCBdCi9D
b250ZW50cyAzIDAgUgovVHlwZSAvUGFnZQovUGFyZW50IDUgMCBSCj4+ZW5kb2JqCjMgMCBvYmo8PAovTGVuZ3RoIDQ3Cj4+c3Ry
ZWFtCnEgNjEyLjAwMDAwMCAwIDAgNzkyLjAwMDAwMCAwIDAgY20gL2ltYWdlIERvIFEKCmVuZHN0cmVhbQplbmRvYmoKNiAwIG9i
ajw8Ci9DcmVhdGlvbkRhdGUgKEQ6MjAyNjExMDQwNTE0MDhaKQovTW9kRGF0ZSAoRDoyMDI2MTEwNDA1MTQwOFopCj4+ZW5kb2Jq
CnhyZWYKMCA3CjAwMDAwMDAwMDAgNjU1MzYgZiAKMDAwMDAwMDE0NCAwMDAwMCBuIAowMDAwMDA4NzM3IDAwMDAwIG4gCjAwMDAw
MDg4OTkgMDAwMDAgbiAKMDAwMDAwMDA0MCAwMDAwMCBuIAowMDAwMDAwMDg3IDAwMDAwIG4gCjAwMDAwMDg5OTQgMDAwMDAgbiAK
dHJhaWxlcgo8PAovUm9vdCA0IDAgUgovU2l6ZSA3Ci9JbmZvIDYgMCBSCj4+CnN0YXJ0eHJlZgo5MDc2CiUlRU9G"""

PPTX_B64 = """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
BgAA0i4AACEAAAAAAAAAAAAAAIABBxUAAHBwdC9zbGlkZU1hc3RlcnMvc2xpZGVNYXN0ZXIxLnhtbFBLAQIUABQAAAAIAMRpZF0Z
y/H5DQEAAMYHAAAsAAAAAAAAAAAAAACAATQcAABwcHQvc2xpZGVNYXN0ZXJzL19yZWxzL3NsaWRlTWFzdGVyMS54bWwucmVsc1BL
AQIUABQAAAAIAMRpZF1LiVBXwAMAAK0MAAAiAAAAAAAAAAAAAACAAYsdAABwcHQvc2xpZGVMYXlvdXRzL3NsaWRlTGF5b3V0MTEu
eG1sUEsBAhQAFAAAAAgAxGlkXYBl4Yi3AAAANgEAAC0AAAAAAAAAAAAAAIABiyEAAHBwdC9zbGlkZUxheW91dHMvX3JlbHMvc2xp
ZGVMYXlvdXQxMS54bWwucmVsc1BLAQIUABQAAAAIAMRpZF0A/ewNKgQAAAURAAAhAAAAAAAAAAAAAACAAY0iAABwcHQvc2xpZGVM
YXlvdXRzL3NsaWRlTGF5b3V0MS54bWxQSwECFAAUAAAACADEaWRdgGXhiLcAAAA2AQAALAAAAAAAAAAAAAAAgAH2JgAAcHB0L3Ns
aWRlTGF5b3V0cy9fcmVscy9zbGlkZUxheW91dDEueG1sLnJlbHNQSwECFAAUAAAACADEaWRdAVfoi20DAACWCwAAIQAAAAAAAAAA
AAAAgAH3JwAAcHB0L3NsaWRlTGF5b3V0cy9zbGlkZUxheW91dDIueG1sUEsBAhQAFAAAAAgAxGlkXYBl4Yi3AAAANgEAACwAAAAA
AAAAAAAAAIABoysAAHBwdC9zbGlkZUxheW91dHMvX3JlbHMvc2xpZGVMYXlvdXQyLnhtbC5yZWxzUEsBAhQAFAAAAAgAxGlkXYtg
7VpjBAAAWBEAACEAAAAAAAAAAAAAAIABpCwAAHBwdC9zbGlkZUxheW91dHMvc2xpZGVMYXlvdXQzLnhtbFBLAQIUABQAAAAIAMRp
ZF2AZeGItwAAADYBAAAsAAAAAAAAAAAAAACAAUYxAABwcHQvc2xpZGVMYXlvdXRzL19yZWxzL3NsaWRlTGF5b3V0My54bWwucmVs
c1BLAQIUABQAAAAIAMRpZF1PyoIcCAQAAGgSAAAhAAAAAAAAAAAAAACAAUcyAABwcHQvc2xpZGVMYXlvdXRzL3NsaWRlTGF5b3V0
NC54bWxQSwECFAAUAAAACADEaWRdgGXhiLcAAAA2AQAALAAAAAAAAAAAAAAAgAGONgAAcHB0L3NsaWRlTGF5b3V0cy9fcmVscy9z
bGlkZUxheW91dDQueG1sLnJlbHNQSwECFAAUAAAACADEaWRd6aTEj+MEAAA2HAAAIQAAAAAAAAAAAAAAgAGPNwAAcHB0L3NsaWRl
TGF5b3V0cy9zbGlkZUxheW91dDUueG1sUEsBAhQAFAAAAAgAxGlkXYBl4Yi3AAAANgEAACwAAAAAAAAAAAAAAIABsTwAAHBwdC9z
bGlkZUxheW91dHMvX3JlbHMvc2xpZGVMYXlvdXQ1LnhtbC5yZWxzUEsBAhQAFAAAAAgAxGlkXS20JvUSAwAAuAgAACEAAAAAAAAA
AAAAAIABsj0AAHBwdC9zbGlkZUxheW91dHMvc2xpZGVMYXlvdXQ2LnhtbFBLAQIUABQAAAAIAMRpZF2AZeGItwAAADYBAAAsAAAA
AAAAAAAAAACAAQNBAABwcHQvc2xpZGVMYXlvdXRzL19yZWxzL3NsaWRlTGF5b3V0Ni54bWwucmVsc1BLAQIUABQAAAAIAMRpZF3r
F5935gIAAGcHAAAhAAAAAAAAAAAAAACAAQRCAABwcHQvc2xpZGVMYXlvdXRzL3NsaWRlTGF5b3V0Ny54bWxQSwECFAAUAAAACADE
aWRdgGXhiLcAAAA2AQAALAAAAAAAAAAAAAAAgAEpRQAAcHB0L3NsaWRlTGF5b3V0cy9fcmVscy9zbGlkZUxheW91dDcueG1sLnJl
bHNQSwECFAAUAAAACADEaWRdzcqK1bIEAADCEgAAIQAAAAAAAAAAAAAAgAEqRgAAcHB0L3NsaWRlTGF5b3V0cy9zbGlkZUxheW91
dDgueG1sUEsBAhQAFAAAAAgAxGlkXYBl4Yi3AAAANgEAACwAAAAAAAAAAAAAAIABG0sAAHBwdC9zbGlkZUxheW91dHMvX3JlbHMv
c2xpZGVMYXlvdXQ4LnhtbC5yZWxzUEsBAhQAFAAAAAgAxGlkXVrTtJJ5BAAAMRIAACEAAAAAAAAAAAAAAIABHEwAAHBwdC9zbGlk
ZUxheW91dHMvc2xpZGVMYXlvdXQ5LnhtbFBLAQIUABQAAAAIAMRpZF2AZeGItwAAADYBAAAsAAAAAAAAAAAAAACAAdRQAABwcHQv
c2xpZGVMYXlvdXRzL19yZWxzL3NsaWRlTGF5b3V0OS54bWwucmVsc1BLAQIUABQAAAAIAMRpZF03xjX4jQMAAM0LAAAiAAAAAAAA
AAAAAACAAdVRAABwcHQvc2xpZGVMYXlvdXRzL3NsaWRlTGF5b3V0MTAueG1sUEsBAhQAFAAAAAgAxGlkXYBl4Yi3AAAANgEAAC0A
AAAAAAAAAAAAAIABolUAAHBwdC9zbGlkZUxheW91dHMvX3JlbHMvc2xpZGVMYXlvdXQxMC54bWwucmVsc1BLAQIUABQAAAAIAMRp
ZF3o5EnROQMAALMkAAAoAAAAAAAAAAAAAACAAaRWAABwcHQvcHJpbnRlclNldHRpbmdzL3ByaW50ZXJTZXR0aW5nczEuYmluUEsB
AhQAFAAAAAgAxGlkXXSQuG+eAQAASgMAABUAAAAAAAAAAAAAAIABI1oAAHBwdC9zbGlkZXMvc2xpZGUxLnhtbFBLAQIUABQAAAAI
AMRpZF0bf+la0gAAAL0BAAAgAAAAAAAAAAAAAACAAfRbAABwcHQvc2xpZGVzL19yZWxzL3NsaWRlMS54bWwucmVsc1BLAQIUABQA
AAAIAMRpZF2S1baFSgAAAE4AAAAUAAAAAAAAAAAAAACAAQRdAABwcHQvbWVkaWEvaW1hZ2UxLnBuZ1BLAQIUABQAAAAIAMRpZF1a
oA6towUAAOMPAAAXAAAAAAAAAAAAAACAAYBdAABkb2NQcm9wcy90aHVtYm5haWwuanBlZ1BLBQYAAAAAJwAnAOULAABYYwAAAAA="""


if __name__ == "__main__":
    unittest.main()
