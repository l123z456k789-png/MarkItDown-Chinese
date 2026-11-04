# MarkItDown-Chinese v0.2.0 (AI Enhanced)

> 基于 Microsoft 开源 MarkItDown 0.1.7 的 Windows 中文外壳。非官方项目，与 Microsoft 无隶属关系。

把 MarkItDown CLI 包装成更适合中文 Windows 的用法：拖拽转换、交互式操作、进度提示、输出防覆盖。可选接入 Xiaomi-OCR-0 与 Qwen3-TTS，全部走 HTTP，不安装 torch/transformers。

## 快速开始

**免安装便携版**：到 [Releases](../../releases/latest) 下载 `MarkItDown-Chinese-Portable-Windows.zip`，解压到普通用户目录（不要放 `Program Files`），双击 `启动 MarkItDown.bat` 或 `start-markitdown.bat`。仅支持 Windows 10/11 x64。

**源码运行**：需要 Windows 和 Python 3.10+。

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install "markitdown[all]"
```

## 功能

- 双击进入交互模式，或把文件拖进窗口/拖到 BAT 上转换。
- 每约 4 秒显示进度心跳；检测 Word/Excel/PowerPoint 占用。
- 结果统一输出到 `output\`；同名自动 `_2`、`_3`，不覆盖。
- 交互命令：`help`、`cli`、`config`、`tts <md>`、`q`。
- 可选 OCR：图片、扫描版 PDF、PPTX 内嵌图。
- 可选 TTS：Markdown 转语音，多段 WAV 自动合并。

## 使用

双击 `启动 MarkItDown.bat`（中文入口）或 `start-markitdown.bat`（ASCII 入口）：

- 直接双击：交互模式，可粘贴路径或拖入文件。
- 拖文件到 BAT：逐个转换。
- `help`：查看支持格式。
- `cli`：进入官方 MarkItDown CLI（`exit` 返回）。
- `config`：编辑 `config.json`。
- `tts output\报告.md`：生成语音到 `output\`。
- `q`：退出。

直接调用官方 CLI：

```bat
.venv\Scripts\markitdown.exe "文件.pdf" -o "output\文件.md"
```

中文和带空格的路径请加双引号。

## AI 增强（可选）

默认关闭。不填接口地址时，行为与普通 MarkItDown 完全一致；接口未启动时自动回退并给出中文提示。

首次运行会自动从 `config.example.json` 生成 `config.json`。`config.json` 已被 `.gitignore` 忽略，只保存在本地；不要把 API Key 写进模板。

### 本地启动服务

需要 NVIDIA GPU（建议 16GB 显存以上）、Docker Desktop（WSL2）和 NVIDIA Container Toolkit：

```bat
docker compose -f ai-server-docker-compose.yml up -d
docker compose -f ai-server-docker-compose.yml logs -f
```

- OCR：`http://127.0.0.1:8000/v1`，模型 `Xiaomi-OCR-0`
- TTS：`http://127.0.0.1:8091/v1`，模型 `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`

首次启动会下载模型，缓存到 `.hf-cache\`。

### 最小配置

只启用 OCR：

```json
{
  "ocr_api_base": "http://127.0.0.1:8000/v1",
  "ocr_model": "Xiaomi-OCR-0"
}
```

只启用 TTS：

```json
{
  "tts_api_base": "http://127.0.0.1:8091/v1",
  "tts_model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
  "tts_voice": "vivian"
}
```

两个都要，就把两组字段合并到同一个 `config.json`。云端 API 同理：改 `*_api_base`，需要鉴权时填 `*_api_key`。

Ollama / LM Studio 也兼容 OpenAI Vision API：

- Ollama：`http://127.0.0.1:11434/v1`
- LM Studio：`http://127.0.0.1:1234/v1`

### 常用配置

| 字段 | 默认 | 说明 |
|---|---|---|
| `enable_ocr` | `true` | OCR 总开关；base 为空时不启用 |
| `enable_ocr_fallback` | `true` | 扫描版 PDF 自动兜底 |
| `ocr_api_base` | 空 | OCR 服务地址 |
| `ocr_api_key` | 空 | OCR 鉴权 |
| `ocr_model` | `Xiaomi-OCR-0` | 与服务端模型名一致 |
| `ocr_min_chars` | `20` | PDF 原生文本低于此值才 OCR |
| `ocr_dpi` | `200` | PDF 渲染 DPI（72–400） |
| `ocr_max_pages` | `50` | 最多 OCR 页数；0 为不限制 |
| `ocr_max_workers` | `2` | 页面并发数（最大 8） |
| `ocr_timeout` | `180` | 单次 OCR 超时秒数 |
| `tts_api_base` | 空 | TTS 服务地址 |
| `tts_api_key` | 空 | TTS 鉴权 |
| `tts_model` | 空 | 留空用服务端默认模型 |
| `tts_voice` | `vivian` | Qwen3-TTS 音色 |
| `tts_language` | `Auto` | 语言；Auto 不发送 |
| `tts_format` | `wav` | wav/mp3/flac/opus/pcm |
| `tts_endpoint` | `/audio/speech` | 自定义 TTS 路径 |
| `tts_max_chars` | `300` | 单次请求最大字符数 |
| `tts_timeout` | `300` | 单段超时秒数 |
| `tts_instructions` | 空 | 可选声音风格指令 |

OCR 细节：

- 图片直接 Base64 发给 Xiaomi-OCR-0。
- PDF 先原生转换，文本过少才逐页渲染 + 并发 OCR。
- PPTX 内嵌图片通过 `llm_client` 自动识别。
- OTSL 表格自动转标准 Markdown 管道表格；失败时原样保留。
- 失败不中断，保留原生结果。

TTS 细节：

- 先剔除代码块、表格线、链接、LaTeX 等不适合朗读的内容。
- 按 `tts_max_chars` 分段请求。
- 多段 WAV 参数一致时合并为单个 `报告.wav`；非 WAV 或参数冲突才保存 `_01`、`_02` 分片。
- 同名不覆盖。

## 支持格式

直接支持：

```text
PDF .pdf        Word .docx        PowerPoint .pptx
Excel .xlsx .xls                  HTML .html .htm
CSV .csv        JSON/XML/文本 .json .xml .txt .md
EPUB .epub      ZIP .zip          RSS/Atom .rss .atom
Jupyter .ipynb
```

有条件支持：扫描版 PDF、图片（需 OCR）、音频（需 ffmpeg + 联网语音识别）、`.msg`、`.xls`（未实测）。

明确不支持：

```text
.doc .ppt .odt .ods .odp .rtf .gif .bmp .tiff
```

`.doc ≠ .docx`，`.ppt ≠ .pptx`；旧格式请先另存为新格式。

## 输出规则

- 统一输出到 `output\`，不存在时自动创建。
- 同名自动 `_2`、`_3`，不覆盖。
- `cli` 模式下 `-o` 指定的文件仍由官方 CLI 直接覆盖。

## 构建便携版

需要 Python 3.12 和 `.venv`：

```bat
.venv\Scripts\python.exe -m pip install -r requirements-portable.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-portable.ps1
```

输出：`dist\MarkItDown-Chinese-Portable-Windows.zip`

构建前会自动运行 `tests/` 下的 unittest，失败则中断。便携版固定 MarkItDown 0.1.7；`config.json` 不打包，首次运行自动生成。

## 限制

- 仅 Windows，依赖 PowerShell 和 `.venv`。
- 不内置 OCR/TTS 模型；AI 增强需要外部 HTTP 服务。
- 不重新实现 MarkItDown 解析能力，格式范围由上游决定。
- 社区项目，与 Microsoft 无隶属或背书关系。

## 许可

MIT License，版权归本项目贡献者所有。上游 MarkItDown 同样使用 MIT License，版权归其原作者所有。
