#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MarkItDown-Chinese 轻量包装器。

原生转换仍然完全由 markitdown 完成。这里只增加两个可选的 HTTP 增强：

1. Xiaomi-OCR-0：OpenAI 兼容的 Vision Chat API，用于图片和扫描版 PDF。
2. Qwen3-TTS：OpenAI 兼容的 /v1/audio/speech API，用于把 Markdown 读成语音。

设计约束：
- 不导入 torch / transformers 等重型库；
- 只使用 markitdown、pypdfium2（PDF 渲染）、Pillow（pypdfium2 转 PNG）
  以及 Python 标准库；
- 未配置接口或接口不可用时，自动回退到原版 MarkItDown 行为。
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import mimetypes
import re
import sys
import urllib.error
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
OUTPUT_DIR = ROOT / "output"
WRAPPER_VERSION = "v0.2.1 (AI Enhanced)"

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
}

DEFAULT_CONFIG: Dict[str, Any] = {
    # OCR：Xiaomi-OCR-0，OpenAI 兼容 Vision API
    "enable_ocr": True,
    "enable_ocr_fallback": True,
    "ocr_api_base": "",
    "ocr_api_key": "",
    "ocr_model": "Xiaomi-OCR-0",
    "ocr_prompt": (
        "Extract all information from the main body of the document image and "
        "represent it in markdown format, ignoring headers and footers. Tables "
        "should be expressed in OTSL format, formulas in the document should be "
        "represented using LATEX format, and the parsing should be organized "
        "according to the reading order."
    ),
    "ocr_timeout": 180,
    "ocr_max_tokens": 4096,
    "ocr_dpi": 200,
    "ocr_max_pages": 50,
    "ocr_max_workers": 2,
    "ocr_min_chars": 20,
    # TTS：Qwen3-TTS，OpenAI 兼容 /v1/audio/speech
    "tts_api_base": "",
    "tts_api_key": "",
    "tts_model": "",
    "tts_voice": "vivian",
    "tts_language": "Auto",
    "tts_format": "wav",
    "tts_endpoint": "/audio/speech",
    "tts_instructions": "",
    "tts_timeout": 300,
    "tts_max_chars": 300,
}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------


def eprint(message: str) -> None:
    """把诊断信息写到 stderr，避免污染转换结果。"""
    if sys.stderr is None:
        return
    try:
        print(message, file=sys.stderr, flush=True)
    except UnicodeEncodeError:
        encoding = sys.stderr.encoding or "utf-8"
        safe = message.encode(encoding, errors="replace").decode(
            encoding, errors="replace"
        )
        sys.stderr.write(safe + "\n")
        sys.stderr.flush()


def print_line(message: str) -> None:
    """把用户可见结果写到 stdout，遇到不可编码字符时替换而不是崩溃。"""
    if sys.stdout is None:
        return
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe = message.encode(encoding, errors="replace").decode(
            encoding, errors="replace"
        )
        sys.stdout.write(safe + "\n")
        sys.stdout.flush()


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "y"}
    if value is None:
        return default
    return bool(value)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_config(path: Path) -> Dict[str, Any]:
    """读取 config.json；不存在时生成默认配置。"""
    config = dict(DEFAULT_CONFIG)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                config.update(data)
            else:
                eprint(f"[配置] {path.name} 顶层不是对象，使用默认配置。")
        except Exception as exc:  # noqa: BLE001 - 配置文件损坏时不能让转换失败
            eprint(f"[配置] 读取 {path.name} 失败，使用默认配置：{exc}")
    else:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            example = ROOT / "config.example.json"
            if example.is_file():
                path.write_bytes(example.read_bytes())
                eprint(f"[配置] 已从 {example.name} 生成：{path}")
            else:
                path.write_text(
                    json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                eprint(f"[配置] 已生成默认配置：{path}")
        except OSError as exc:
            eprint(f"[配置] 无法生成 {path.name}，使用内存默认配置：{exc}")
    return config


def _http_post_json(
    url: str,
    payload: Dict[str, Any],
    api_key: str = "",
    timeout: int = 180,
) -> Tuple[bytes, Any]:
    """POST JSON，返回 (响应体, 响应头)。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json; charset=utf-8")
    request.add_header("Accept", "application/json, audio/*, */*")
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib.request.urlopen(request, timeout=max(1, timeout)) as response:
            return response.read(), response.headers
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(
            f"HTTP {exc.code}: {detail or exc.reason}"
        ) from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接接口：{exc.reason}") from None
    except TimeoutError:
        raise RuntimeError("接口请求超时") from None


def _strip_outer_fence(text: str) -> str:
    """去掉模型偶尔包在整段输出外面的 ```markdown 围栏。"""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


_OTSL_TOKEN_RE = re.compile(r"<(fcel|ecel|lcel|ucel|xcel|nl)>", re.IGNORECASE)
_OTSL_BLOCK_RE = re.compile(
    r"<(table|otsl)(?:\s[^>]*)?>(.*?)</\1>",
    re.IGNORECASE | re.DOTALL,
)


def _parse_otsl_rows(block: str) -> List[List[Tuple[str, str]]]:
    parts = _OTSL_TOKEN_RE.split(block)
    rows: List[List[Tuple[str, str]]] = []
    row: List[Tuple[str, str]] = []
    for index in range(1, len(parts), 2):
        tag = parts[index].lower()
        content = parts[index + 1] if index + 1 < len(parts) else ""
        if tag == "nl":
            if row:
                rows.append(row)
                row = []
        else:
            row.append((tag, content.strip()))
    if row:
        rows.append(row)
    return rows


def _otsl_rows_to_grid(rows: List[List[Tuple[str, str]]]) -> List[List[str]]:
    grid: List[List[str]] = []
    width = 0
    for row in rows:
        values: List[str] = []
        for column, (kind, content) in enumerate(row):
            if kind == "fcel":
                value = content
            elif kind == "ecel":
                value = ""
            elif kind == "lcel":
                value = values[column - 1] if column > 0 else ""
            elif kind == "ucel":
                value = (
                    grid[-1][column]
                    if grid and column < len(grid[-1])
                    else ""
                )
            elif kind == "xcel":
                above = (
                    grid[-1][column]
                    if grid and column < len(grid[-1])
                    else ""
                )
                left = values[column - 1] if column > 0 else ""
                value = above or left
            else:
                value = content
            values.append(value)

        grid.append(values)
        width = max(width, len(values))

    if width == 0:
        return []

    for row in grid:
        row.extend([""] * (width - len(row)))

    while width > 0 and all(not row[width - 1].strip() for row in grid):
        width -= 1
    if width == 0:
        return []

    grid = [row[:width] for row in grid]
    while grid and all(not cell.strip() for cell in grid[0]):
        grid.pop(0)
    while grid and all(not cell.strip() for cell in grid[-1]):
        grid.pop()
    return grid


def _escape_markdown_cell(value: str) -> str:
    # 只转义未转义的竖线；不要动 LaTeX 里的反斜杠。
    value = re.sub(r"(?<!\\)\|", r"\\|", value.strip())
    value = re.sub(r"\s*\r?\n\s*", "<br>", value)
    return value


def _render_markdown_table(grid: List[List[str]]) -> str:
    if not grid:
        return ""
    width = len(grid[0])
    lines = [
        "| " + " | ".join(_escape_markdown_cell(cell) for cell in grid[0]) + " |",
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    for row in grid[1:]:
        lines.append(
            "| " + " | ".join(_escape_markdown_cell(cell) for cell in row) + " |"
        )
    return "\n".join(lines)


def convert_otsl_to_markdown(text: str) -> str:
    """把 Xiaomi-OCR-0 的 OTSL 表格块转成标准 Markdown 管道表格。

    支持 <table> / <otsl> 包装，以及 fcel / ecel / lcel / ucel / xcel / nl
    六种标签。没有 OTSL 标签的文本原样返回。
    """
    if not text or "<" not in text:
        return text
    if not _OTSL_TOKEN_RE.search(text):
        return text

    def replace_block(match: re.Match) -> str:
        rows = _parse_otsl_rows(match.group(2))
        grid = _otsl_rows_to_grid(rows)
        if not grid:
            return match.group(0)
        return _render_markdown_table(grid)

    converted, count = _OTSL_BLOCK_RE.subn(replace_block, text)
    return converted if count else text


def _content_to_text(content: Any) -> str:
    """兼容 OpenAI content 为字符串或分段数组的两种返回。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif "text" in item:
                    parts.append(str(item["text"]))
        return "".join(parts)
    return str(content or "")


# ---------------------------------------------------------------------------
# 原生转换
# ---------------------------------------------------------------------------


def convert_native(
    path: Path,
    config: Optional[Dict[str, Any]] = None,
    use_llm: bool = True,
) -> str:
    """调用 markitdown 库完成原生转换，行为与 CLI 的 -o 写文件一致。

    配置了 OCR 时，同时传入一个极简 llm_client，让 .pptx 等格式里的
    内嵌图片也能走 Xiaomi-OCR-0。
    """
    from markitdown import MarkItDown

    converter = None
    if use_llm and config is not None and _ocr_ready(config):
        model = (
            str(config.get("ocr_model") or "Xiaomi-OCR-0").strip()
            or "Xiaomi-OCR-0"
        )
        prompt = str(
            config.get("ocr_prompt") or DEFAULT_CONFIG["ocr_prompt"]
        ).strip()
        try:
            converter = MarkItDown(
                enable_plugins=False,
                llm_client=_UrllibOpenAIClient(config),
                llm_model=model,
                llm_prompt=prompt,
            )
        except TypeError as exc:
            eprint(f"[OCR] 当前 MarkItDown 不支持 llm_client，跳过内嵌图识别：{exc}")

    if converter is None:
        converter = MarkItDown(enable_plugins=False)

    result = converter.convert(str(path))
    markdown = getattr(result, "markdown", None)
    if markdown is None:
        markdown = getattr(result, "text_content", None)
    return markdown or ""


def write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


# ---------------------------------------------------------------------------
# Xiaomi-OCR-0
# ---------------------------------------------------------------------------


def _ocr_ready(config: Dict[str, Any]) -> bool:
    return _as_bool(config.get("enable_ocr"), True) and bool(
        str(config.get("ocr_api_base") or "").strip()
    )


def _pdf_fallback_ready(config: Dict[str, Any]) -> bool:
    return _ocr_ready(config) and _as_bool(
        config.get("enable_ocr_fallback"), True
    )


def _ocr_chat_url(base: str) -> str:
    base = base.strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _image_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    if mime and mime.startswith("image/"):
        return mime
    return "image/png"


def _ocr_request(
    image_bytes: bytes,
    mime: str,
    prompt: str,
    model: str,
    config: Dict[str, Any],
) -> str:
    """底层 OCR 请求：Base64 图片 → OpenAI 兼容 Vision API → 文本。"""
    base = str(config.get("ocr_api_base") or "").strip()
    if not base:
        raise RuntimeError("未配置 ocr_api_base")

    model = str(model or config.get("ocr_model") or "Xiaomi-OCR-0").strip()
    prompt = str(prompt or config.get("ocr_prompt") or DEFAULT_CONFIG["ocr_prompt"]).strip()
    encoded = base64.b64encode(image_bytes).decode("ascii")
    data_uri = f"data:{mime};base64,{encoded}"

    payload: Dict[str, Any] = {
        "model": model or "Xiaomi-OCR-0",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": data_uri},
                    },
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": _as_int(config.get("ocr_max_tokens"), 4096),
        "stream": False,
    }

    body, _headers = _http_post_json(
        _ocr_chat_url(base),
        payload,
        api_key=str(config.get("ocr_api_key") or ""),
        timeout=_as_int(config.get("ocr_timeout"), 180),
    )

    try:
        data = json.loads(body.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        snippet = body.decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"OCR 接口返回非 JSON：{snippet}") from exc

    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"OCR 接口错误：{data['error']}")

    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices:
        raise RuntimeError("OCR 接口未返回 choices")

    first = choices[0] or {}
    message = first.get("message") or {}
    text = _content_to_text(message.get("content"))
    if not text.strip():
        text = str(first.get("text") or "")

    text = _strip_outer_fence(text)
    if not text.strip():
        raise RuntimeError("OCR 接口返回空内容")
    return convert_otsl_to_markdown(text.strip())


def ocr_image_bytes(image_bytes: bytes, mime: str, config: Dict[str, Any]) -> str:
    """把一张图片发给 Xiaomi-OCR-0，返回 Markdown。"""
    return _ocr_request(
        image_bytes,
        mime,
        str(config.get("ocr_prompt") or DEFAULT_CONFIG["ocr_prompt"]),
        str(config.get("ocr_model") or "Xiaomi-OCR-0"),
        config,
    )


def ocr_image_file(path: Path, config: Dict[str, Any]) -> str:
    return ocr_image_bytes(path.read_bytes(), _image_mime(path), config)


def _decode_data_uri(uri: str) -> Tuple[bytes, str]:
    if not uri.startswith("data:") or "," not in uri:
        raise RuntimeError("llm_client 只支持 data: URI 图片")
    header, payload = uri.split(",", 1)
    mime = header[5:].split(";", 1)[0].strip() or "image/png"
    try:
        return base64.b64decode(payload), mime
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"无法解析 data: URI：{exc}") from None


def _parse_openai_image_messages(
    messages: Any,
) -> Tuple[bytes, str, str]:
    """从 MarkItDown 传来的 OpenAI messages 中提取图片、MIME 和提示词。"""
    texts: List[str] = []
    image_bytes: Optional[bytes] = None
    image_mime = "image/png"

    if not isinstance(messages, list):
        raise RuntimeError("llm_client 收到的 messages 不是数组")

    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            texts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                texts.append(str(item.get("text", "")))
            elif item_type == "image_url":
                image_url = item.get("image_url")
                if isinstance(image_url, dict):
                    image_url = image_url.get("url")
                if isinstance(image_url, str):
                    image_bytes, image_mime = _decode_data_uri(image_url)

    if image_bytes is None:
        raise RuntimeError("llm_client 只支持包含 image_url 的消息")
    prompt = "\n".join(text for text in texts if text).strip()
    return image_bytes, image_mime, prompt


class _UrllibChatCompletions:
    """模拟 openai client.chat.completions.create 的最小接口。"""

    def __init__(self, config: Dict[str, Any]):
        self._config = config

    def create(
        self,
        model: Optional[str] = None,
        messages: Any = None,
        **_kwargs: Any,
    ) -> Any:
        image_bytes, mime, prompt = _parse_openai_image_messages(messages)
        if not prompt:
            prompt = str(
                self._config.get("ocr_prompt") or DEFAULT_CONFIG["ocr_prompt"]
            )
        text = _ocr_request(
            image_bytes,
            mime,
            prompt,
            str(model or self._config.get("ocr_model") or "Xiaomi-OCR-0"),
            self._config,
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
        )


class _UrllibChat:
    def __init__(self, config: Dict[str, Any]):
        self.completions = _UrllibChatCompletions(config)


class _UrllibOpenAIClient:
    """只实现 MarkItDown 需要的那一小部分 OpenAI 客户端。"""

    def __init__(self, config: Dict[str, Any]):
        self.chat = _UrllibChat(config)


def _pdf_page_count(path: Path) -> int:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    try:
        return len(document)
    finally:
        document.close()


def _iter_pdf_pngs(
    path: Path, dpi: int, limit: int
) -> Iterable[Tuple[int, bytes]]:
    """逐页渲染 PDF，产出 (页码, PNG 字节)。只在主线程调用。"""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    try:
        total = len(document)
        page_limit = total if limit <= 0 else min(total, limit)
        for index in range(page_limit):
            page = document[index]
            bitmap = None
            image = None
            try:
                bitmap = page.render(scale=dpi / 72.0)
                image = bitmap.to_pil()
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                yield index + 1, buffer.getvalue()
            finally:
                if image is not None:
                    try:
                        image.close()
                    except Exception:  # noqa: BLE001
                        pass
                if bitmap is not None:
                    try:
                        bitmap.close()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    page.close()
                except Exception:  # noqa: BLE001
                    pass
    finally:
        document.close()


def ocr_pdf(path: Path, config: Dict[str, Any]) -> str:
    """把扫描版 PDF 逐页渲染后并发请求 OCR，按页序拼接。"""
    dpi = _as_int(config.get("ocr_dpi"), 200)
    dpi = max(72, min(dpi, 400))
    workers = _as_int(config.get("ocr_max_workers"), 2)
    workers = max(1, min(workers, 8))
    max_pages = max(0, _as_int(config.get("ocr_max_pages"), 50))

    total = _pdf_page_count(path)
    if total <= 0:
        raise RuntimeError("PDF 没有页面")
    limit = total if max_pages <= 0 else min(total, max_pages)

    suffix = f"，按 ocr_max_pages 截断为 {limit} 页" if limit < total else ""
    eprint(
        f"[OCR] 共 {total} 页{suffix}；DPI={dpi}，并发={workers}，逐页请求 Xiaomi-OCR-0..."
    )

    results: Dict[int, str] = {}
    iterator = _iter_pdf_pngs(path, dpi, limit)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while True:
            batch: List[Tuple[int, bytes]] = []
            try:
                for _ in range(workers):
                    batch.append(next(iterator))
            except StopIteration:
                pass
            if not batch:
                break

            futures = [
                (page_no, pool.submit(ocr_image_bytes, png, "image/png", config))
                for page_no, png in batch
            ]
            for page_no, future in futures:
                try:
                    results[page_no] = future.result()
                    eprint(f"[OCR] 第 {page_no} 页完成")
                except Exception as exc:  # noqa: BLE001
                    eprint(f"[OCR] 第 {page_no} 页失败：{exc}")

    if not results:
        raise RuntimeError("所有页面的 OCR 均失败")

    return "\n\n---\n\n".join(results[page_no] for page_no in sorted(results)).strip()


def convert_file(path: Path, config: Dict[str, Any]) -> str:
    """原生转换 + 可选 OCR 增强。任何 OCR 故障都回退到原生结果。"""
    extension = path.suffix.lower()

    # 图片：配置了 OCR 就直接走 Vision API，失败再回退原生转换。
    if extension in IMAGE_EXTENSIONS and _ocr_ready(config):
        try:
            eprint(f"[OCR] 图片识别：{path.name}")
            text = ocr_image_file(path, config)
            if text.strip():
                return text
        except Exception as exc:  # noqa: BLE001
            eprint(f"[OCR] 图片识别失败，回退原生转换：{exc}")
        # 图片已经尝试过 OCR，回退时不再把 llm_client 传进去，避免重复请求。
        return convert_native(path, config, use_llm=False)

    # 扫描版 PDF：先原生转换，文本过少才逐页 OCR。
    if extension == ".pdf" and _pdf_fallback_ready(config):
        native_text = ""
        native_error: Optional[Exception] = None
        try:
            native_text = convert_native(path, config)
        except Exception as exc:  # noqa: BLE001
            native_error = exc
            eprint(f"[OCR] 原生 PDF 转换失败：{exc}")

        min_chars = max(0, _as_int(config.get("ocr_min_chars"), 20))
        low_text = (
            min_chars > 0
            and len(re.sub(r"\s+", "", native_text or "")) < min_chars
        )
        if low_text:
            try:
                ocr_text = ocr_pdf(path, config)
                if ocr_text.strip():
                    return ocr_text
            except Exception as exc:  # noqa: BLE001
                eprint(f"[OCR] PDF 兜底失败，保留原生结果：{exc}")

        if native_error is not None:
            raise native_error
        return native_text

    return convert_native(path, config)


# ---------------------------------------------------------------------------
# Qwen3-TTS
# ---------------------------------------------------------------------------


def clean_markdown_for_tts(text: str) -> str:
    """去掉不适合朗读的 Markdown / LaTeX / 表格装饰。"""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"~~~.*?~~~", " ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.S)
    text = re.sub(r"\\\[.*?\\\]", " ", text, flags=re.S)
    text = re.sub(r"\\\(.*?\\\)", " ", text, flags=re.S)
    text = re.sub(r"\$[^$\n]+\$", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = text.replace("^", " ")

    lines: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.fullmatch(r"[-*_]{3,}", line):
            continue
        if re.fullmatch(r"\|?[\s:|-]+\|?", line) and "|" in line:
            continue

        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^>\s?", "", line)
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        line = line.replace("|", "，")
        line = re.sub(r"(\*\*|__)(.*?)\1", r"\2", line)
        line = re.sub(r"(\*|_)(.*?)\1", r"\2", line)
        line = re.sub(r"~~(.*?)~~", r"\1", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)

    return "\n".join(lines).strip()


def split_for_tts(text: str, max_chars: int) -> List[str]:
    """按句号/换行切分，再按长度合并成适合单次 TTS 请求的段落。"""
    max_chars = max(50, max_chars)
    chunks: List[str] = []
    current = ""

    parts = re.split(r"(?<=[。！？!?；;])|(?<=\.)\s+|\n+", text)
    for part in parts:
        part = part.strip()
        if not part:
            continue

        if len(part) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(part), max_chars):
                chunks.append(part[start : start + max_chars])
            continue

        if not current:
            current = part
        elif len(current) + 1 + len(part) <= max_chars:
            current = f"{current} {part}"
        else:
            chunks.append(current)
            current = part

    if current:
        chunks.append(current)
    return chunks


def _tts_speech_url(config: Dict[str, Any]) -> str:
    base = str(config.get("tts_api_base") or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("未配置 tts_api_base")
    if base.endswith("/audio/speech"):
        return base
    endpoint = str(config.get("tts_endpoint") or "/audio/speech").strip()
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    return base + endpoint


def _decode_base64_audio(value: str) -> bytes:
    if value.startswith("data:") and "," in value:
        value = value.split(",", 1)[1]
    return base64.b64decode(value)


def tts_request(text: str, config: Dict[str, Any]) -> bytes:
    """请求 OpenAI 兼容的 /v1/audio/speech，返回音频字节。"""
    payload: Dict[str, Any] = {
        "input": text,
        "voice": str(config.get("tts_voice") or "vivian"),
        "response_format": str(config.get("tts_format") or "wav"),
    }

    model = str(config.get("tts_model") or "").strip()
    if model:
        payload["model"] = model

    language = str(config.get("tts_language") or "").strip()
    if language and language.lower() != "auto":
        payload["language"] = language

    instructions = str(config.get("tts_instructions") or "").strip()
    if instructions:
        payload["instructions"] = instructions

    body, headers = _http_post_json(
        _tts_speech_url(config),
        payload,
        api_key=str(config.get("tts_api_key") or ""),
        timeout=_as_int(config.get("tts_timeout"), 300),
    )

    content_type = headers.get_content_type() if headers is not None else ""
    if content_type == "application/json" or body.lstrip()[:1] == b"{":
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:  # noqa: BLE001
            data = None
        if isinstance(data, dict):
            for key in ("audio", "audio_data", "data"):
                value = data.get(key)
                if isinstance(value, str) and value:
                    try:
                        return _decode_base64_audio(value)
                    except Exception:  # noqa: BLE001
                        pass
            audio_url = data.get("url") or data.get("audio_url")
            if isinstance(audio_url, str) and audio_url.startswith(
                ("http://", "https://")
            ):
                with urllib.request.urlopen(
                    audio_url,
                    timeout=_as_int(config.get("tts_timeout"), 300),
                ) as response:
                    return response.read()
            raise RuntimeError(
                f"TTS 接口返回 JSON 但没有音频数据：{str(data)[:300]}"
            )

    if not body:
        raise RuntimeError("TTS 接口返回空音频")
    return body


def _audio_paths(
    out_dir: Path, stem: str, extension: str, count: int
) -> List[Path]:
    """生成不覆盖已有文件的音频路径。"""

    def candidates(suffix: str) -> List[Path]:
        if count == 1:
            return [out_dir / f"{stem}{suffix}.{extension}"]
        return [
            out_dir / f"{stem}{suffix}_{index:02d}.{extension}"
            for index in range(1, count + 1)
        ]

    suffix = ""
    number = 2
    while any(path.exists() for path in candidates(suffix)):
        suffix = f"_{number}"
        number += 1
        if number > 9999:
            raise RuntimeError("同名音频文件过多，已停止")
    return candidates(suffix)


def _read_wav(data: bytes) -> Optional[Tuple[Tuple[int, int, int, str, str], bytes]]:
    """读取 WAV 参数和帧；不是有效 WAV 时返回 None。"""
    try:
        with wave.open(io.BytesIO(data), "rb") as reader:
            params = (
                reader.getnchannels(),
                reader.getsampwidth(),
                reader.getframerate(),
                reader.getcomptype(),
                reader.getcompname(),
            )
            frames = reader.readframes(reader.getnframes())
            return params, frames
    except (wave.Error, EOFError, OSError):
        return None


def _merge_wav_chunks(audio_chunks: List[bytes], output_path: Path) -> bool:
    """参数一致时把多段 WAV 帧合并成单个文件，返回是否成功。"""
    parsed: List[Tuple[Tuple[int, int, int, str, str], bytes]] = []
    for data in audio_chunks:
        item = _read_wav(data)
        if item is None:
            return False
        parsed.append(item)

    first_params = parsed[0][0]
    if any(item[0] != first_params for item in parsed):
        return False

    frames = b"".join(item[1] for item in parsed)
    nchannels, sampwidth, framerate, comptype, compname = first_params
    with wave.open(str(output_path), "wb") as writer:
        writer.setnchannels(nchannels)
        writer.setsampwidth(sampwidth)
        writer.setframerate(framerate)
        writer.setcomptype(comptype, compname)
        writer.writeframes(frames)
    return True


def tts_file(markdown_path: Path, config: Dict[str, Any]) -> List[Path]:
    """清洗 Markdown，分段请求 Qwen3-TTS，保存到 output/。

    多段且均为参数一致的 WAV 时，合并为单个 .wav；否则回退为分片保存。
    """
    text = markdown_path.read_text(encoding="utf-8", errors="replace")
    cleaned = clean_markdown_for_tts(text)
    if not cleaned.strip():
        raise RuntimeError("Markdown 清洗后没有可朗读文本")

    max_chars = _as_int(config.get("tts_max_chars"), 300)
    chunks = split_for_tts(cleaned, max_chars)
    if not chunks:
        raise RuntimeError("没有可朗读文本")

    audio_format = str(config.get("tts_format") or "wav").strip().lower().lstrip(".")
    if audio_format not in {"wav", "mp3", "flac", "opus", "pcm"}:
        audio_format = "wav"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    eprint(f"[TTS] 共 {len(chunks)} 段，开始请求 Qwen3-TTS...")
    audio_chunks: List[bytes] = []
    for index, chunk in enumerate(chunks, start=1):
        eprint(f"[TTS] 第 {index}/{len(chunks)} 段，{len(chunk)} 字...")
        audio_chunks.append(tts_request(chunk, config))

    if audio_format == "wav" and len(audio_chunks) > 1:
        merged_path = _audio_paths(
            OUTPUT_DIR, markdown_path.stem, "wav", 1
        )[0]
        if _merge_wav_chunks(audio_chunks, merged_path):
            print_line(f"[TTS] 已合并 {len(audio_chunks)} 段：{merged_path}")
            return [merged_path]
        eprint("[TTS] WAV 参数不一致或数据无效，改为分片保存。")

    paths = _audio_paths(
        OUTPUT_DIR, markdown_path.stem, audio_format, len(audio_chunks)
    )
    for index, (audio, output_path) in enumerate(zip(audio_chunks, paths), start=1):
        output_path.write_bytes(audio)
        print_line(f"[TTS] 已保存：{output_path}")

    return paths


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def _markitdown_version() -> str:
    try:
        from importlib.metadata import version

        return version("markitdown")
    except Exception:  # noqa: BLE001
        return "0.1.7"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"MarkItDown-Chinese {WRAPPER_VERSION}"
            "（原生转换 + 可选 OCR/TTS）"
        )
    )
    parser.add_argument(
        "--version",
        action="version",
        version=(
            f"MarkItDown-Chinese {WRAPPER_VERSION}"
            f" / MarkItDown {_markitdown_version()}"
        ),
    )
    parser.add_argument("input", nargs="?", help="输入文件")
    parser.add_argument("-o", "--output", help="Markdown 输出路径")
    parser.add_argument(
        "--tts",
        action="store_true",
        help="把 Markdown 文件合成为语音，保存到 output/",
    )
    parser.add_argument(
        "--config",
        help="配置文件路径（默认使用脚本同目录的 config.json）",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = (
        Path(args.config).expanduser().resolve() if args.config else CONFIG_PATH
    )
    config = load_config(config_path)

    if args.tts:
        if args.output:
            eprint("[TTS] 提示：--tts 模式固定保存到 output/，-o 将被忽略。")
        if not args.input:
            eprint("用法：python markitdown_wrapper.py --tts <Markdown 文件>")
            return 2
        markdown_path = Path(args.input).expanduser()
        if not markdown_path.is_file():
            eprint(f"[TTS] 找不到文件：{markdown_path}")
            return 2
        try:
            tts_file(markdown_path, config)
        except Exception as exc:  # noqa: BLE001
            eprint(f"[TTS] 失败：{exc}")
            return 1
        return 0

    if not args.input:
        eprint("用法：python markitdown_wrapper.py <输入文件> [-o 输出.md]")
        return 2

    source = Path(args.input).expanduser()
    if not source.is_file():
        eprint(f"[转换] 找不到文件：{source}")
        return 2

    try:
        text = convert_file(source, config)
    except Exception as exc:  # noqa: BLE001
        eprint(f"{type(exc).__name__}: {exc}")
        return 1

    try:
        if args.output:
            write_markdown(Path(args.output).expanduser(), text)
        else:
            encoding = sys.stdout.encoding or "utf-8"
            print(
                text.encode(encoding, errors="replace").decode(
                    encoding, errors="replace"
                )
            )
    except Exception as exc:  # noqa: BLE001
        eprint(f"[转换] 写入输出失败：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
