# MarkItDown-Chinese v0.2.0 (AI Enhanced) | Windows 文档转换助手

> 本项目包装器版本：v0.2.0 (AI Enhanced) · 底层转换引擎：Microsoft MarkItDown 0.1.7
>
> 非官方社区项目，不隶属于 Microsoft，也不是 Microsoft 官方产品。

MarkItDown-Chinese 是一个基于微软开源 [MarkItDown](https://github.com/microsoft/markitdown) CLI 的 Windows 中文使用体验增强工具。它不重新实现文档转换引擎，只把现有 CLI 包装成更适合中文 Windows 用户的操作方式：拖拽转换、交互式操作、进度提示和输出文件名自动管理。

## 普通用户：免安装便携版

不想安装 Python？请到 [Releases](https://github.com/l123z456k789-png/MarkItDown-Chinese/releases/latest) 下载：

```text
MarkItDown-Chinese-Portable-Windows.zip
```

解压到普通用户目录（不要放在 `Program Files`），双击 `启动 MarkItDown.bat` 或 `start-markitdown.bat` 即可。便携版已包含 Python 运行时、MarkItDown 和依赖，不需要执行 pip，也不需要访问 Microsoft 原仓库。

> 便携版仅提供 Windows 10/11 x64。

## 功能

- 双击 `启动 MarkItDown.bat` 或 `start-markitdown.bat` 进入交互模式。
- 把文件拖进窗口，或把文件拖到入口脚本图标上，即可转换。
- 转换期间每约 4 秒显示一次进度心跳。
- 结果统一输出到 `output\`；同名文件自动使用 `_2`、`_3` 等后缀，不覆盖已有文件。
- 检测文件是否被 Word / Excel / PowerPoint 占用，并给出中文提示。
- 输入 `help` 查看支持格式；输入 `cli` 进入官方 CLI（便携版使用包内运行时，源码版使用 `.venv`）；输入 `q` 退出。
- 转换失败时显示 MarkItDown 原始错误信息和退出码。
- 可选 AI 增强：Xiaomi-OCR-0 识别图片/扫描 PDF/PPTX 内嵌图，Qwen3-TTS 把 Markdown 读成语音；不安装任何重型深度学习库。

## 源码运行（需要 Python）

如果你下载的是便携版，可以跳过本节。源码版需要 Windows 和 Python 3.10+，并确保 `python` 在 PATH 中。在本目录打开终端，执行：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install "markitdown[all]"
```

本仓库不锁定 MarkItDown 版本。升级到最新版：

```bat
.venv\Scripts\python.exe -m pip install -U "markitdown[all]"
```

OCR 兜底使用 `pypdfium2` 渲染 PDF；它和 Pillow 已随 `markitdown[all]` 的 PDF 依赖安装。便携版构建会额外校验这两个库。

## 使用

双击 `启动 MarkItDown.bat`（中文入口）或 `start-markitdown.bat`（ASCII 入口）。两者共用同一套启动逻辑：

- 直接双击：进入交互模式，可粘贴路径或把文件拖进窗口。
- 把文件拖到入口脚本上：逐个转换。
- 交互模式命令：`help`、`cli`、`q`。
- 也可以直接调用 `.venv` 里的官方 CLI：

```bat
.venv\Scripts\markitdown.exe "文件.pdf" -o "output\文件.md"
```

中文和带空格的路径请使用双引号。

## 构建便携版（开发者）

需要已安装 Python 3.12 并创建 `.venv`：

```bat
.venv\Scripts\python.exe -m pip install -r requirements-portable.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-portable.ps1
```

输出：

```text
dist\MarkItDown-Chinese-Portable-Windows.zip
```

构建脚本会复制当前 Python 运行时和 `.venv` 依赖，生成免安装包；构建产物不会提交进 Git。便携版固定使用 MarkItDown 0.1.7，以保证与实测环境一致。

构建会一并打包 `markitdown_wrapper.py`、`ai-server-docker-compose.yml` 和 `config.example.json`；`config.json` 不会打包，首次运行时自动从模板复制生成。

## 支持格式

以下为 MarkItDown 0.1.7 的本机审计和实测结果；由于安装不锁定版本，升级后行为可能变化，最终以官方文档为准。

**直接支持：**

```text
PDF .pdf            Word .docx          PowerPoint .pptx
Excel .xlsx         HTML .html .htm     CSV .csv
JSON/XML/文本 .json .xml .txt .md       EPUB .epub
ZIP .zip            RSS/Atom .rss .atom Jupyter .ipynb
```

**有条件支持：**

- 扫描版 PDF：配置 OCR 后自动逐页兜底；未配置时没有 OCR，纯图片扫描件可能提取不到正文。
- 图片 `.jpg .jpeg .png`：配置 OCR 后走 Xiaomi-OCR-0；未配置且没有 exiftool / OCR / LLM 时，实测输出为空文件。
- 音频 `.wav .mp3 .m4a .mp4`：需要 ffmpeg 和联网语音识别，未实测。
- Outlook `.msg`：转换器和依赖存在，未用真实样本实测。
- `.xls`：转换器和 `xlrd` 依赖已确认存在，但本轮没有真实样本，未实测。

**明确不支持：**

```text
.doc  .ppt  .odt  .ods  .odp  .rtf  .gif  .bmp  .tiff
```

注意：`.doc ≠ .docx`，`.ppt ≠ .pptx`。旧格式请先用 Office 另存为 `.docx` / `.pptx`。未列出的扩展名不会被提前拦截，会交给 MarkItDown 按文件内容尝试。

## 输出规则

- 转换模式和拖拽模式统一输出到 `output\`，目录不存在时自动创建。
- 如果 `output\报告.md` 已存在，自动改用 `报告_2.md`、`报告_3.md`，不会覆盖已有文件。
- 在 `cli` 模式下用 `-o` 手动指定的文件仍会被 MarkItDown 直接覆盖。

## AI 增强（可选）

默认关闭（接口地址为空）。源码仓库附带 `config.example.json`；首次运行会自动复制为 `config.json`，填入接口后生效。接口未配置或服务未启动时，自动回退到原生 MarkItDown，不报错、不中断。

### 本地启动服务

需要 NVIDIA GPU（建议 16GB 显存以上）、Docker Desktop（WSL2 后端）和 NVIDIA Container Toolkit。

```bat
docker compose -f ai-server-docker-compose.yml up -d
docker compose -f ai-server-docker-compose.yml logs -f
```

首次启动会下载模型，缓存到 `.hf-cache\`。启动后把 `config.json` 改成：

```json
{
  "ocr_api_base": "http://127.0.0.1:8000/v1",
  "ocr_model": "Xiaomi-OCR-0",
  "tts_api_base": "http://127.0.0.1:8091/v1",
  "tts_model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
  "tts_voice": "vivian"
}
```

也可以只填其中一项。云端或远程 API 同理：把 `*_api_base` 换成对应地址，需要鉴权时填 `*_api_key`。

常见 OCR 接口：

- vLLM（本仓库 compose）：`http://127.0.0.1:8000/v1`，模型 `Xiaomi-OCR-0`
- Ollama：`http://127.0.0.1:11434/v1`，模型填 `ollama list` 中的实际名称
- LM Studio：`http://127.0.0.1:1234/v1`，模型填当前加载的模型标识

### OCR

- 图片：配置后直接把图片以 Base64 发送给 Xiaomi-OCR-0。
- PDF：先走原生 MarkItDown；纯文本字数少于 `ocr_min_chars`（默认 20）时，用 pypdfium2 逐页渲染，再并发请求 OCR。
- 默认最多处理 `ocr_max_pages` 页（默认 50，0 表示不限制），每页 DPI 200，并发 2。
- Xiaomi-OCR-0 官方推荐表格输出 OTSL、公式输出 LaTeX；OTSL 表格会自动转换为标准 Markdown 管道表格，转换失败时原样保留。
- 配置 OCR 后，`.pptx` 等文档里的内嵌图片也会通过 `llm_client` 调用 Xiaomi-OCR-0，不再只依赖 alt text。
- OCR 失败不会中断转换，保留原生结果并给出中文提示。

### TTS

在交互模式输入：

```text
tts output\报告.md
```

或直接调用：

```bat
.venv\Scripts\python.exe markitdown_wrapper.py --tts "output\报告.md"
```

会先剔除代码块、表格线、链接、LaTeX 等不适合朗读的内容，再按 `tts_max_chars` 分段请求 Qwen3-TTS，音频保存到 `output\`。多段 WAV 参数一致时自动合并为单个 `报告.wav`；只有非 WAV 格式或参数冲突时才回退为 `报告_01.wav`、`报告_02.wav` 分片。同名不覆盖。

### 配置要点

| 字段 | 默认 | 说明 |
|---|---|---|
| `enable_ocr` | `true` | OCR 总开关；`ocr_api_base` 为空时仍不启用 |
| `enable_ocr_fallback` | `true` | 仅控制扫描版 PDF 兜底 |
| `ocr_api_base` | 空 | 例如 `http://127.0.0.1:8000/v1` |
| `ocr_model` | `Xiaomi-OCR-0` | vLLM 的 served-model-name |
| `ocr_min_chars` | `20` | PDF 原生文本低于此值触发 OCR |
| `ocr_dpi` | `200` | PDF 渲染 DPI，范围 72–400 |
| `tts_api_base` | 空 | 例如 `http://127.0.0.1:8091/v1` |
| `tts_model` | 空 | 留空则使用服务端默认模型 |
| `tts_voice` | `vivian` | Qwen3-TTS 预置音色 |
| `tts_format` | `wav` | `wav` / `mp3` / `flac` / `opus` / `pcm` |
| `tts_max_chars` | `300` | 单次请求的最大字符数 |

> `config.json` 已加入 `.gitignore`，只保存在本地；`config.example.json` 才是纳入 Git 的模板，请不要把 API Key 写进模板。

## 限制

- 仅支持 Windows，依赖 PowerShell 和 `.venv`。
- 不内置 OCR/TTS 模型；可选 AI 增强需要外部 HTTP 服务，未配置时保持原版离线行为。
- 不重新实现 MarkItDown 的解析能力，格式支持范围由上游决定。
- 本项目是社区工具，与 Microsoft 没有隶属或背书关系。

## 上游与许可

- 上游项目：[microsoft/markitdown](https://github.com/microsoft/markitdown)
- 本仓库不包含微软上游 MarkItDown 的源代码。
- 本项目使用 MIT License，版权归 `l123z456k789-png` 所有；详见 [LICENSE](LICENSE)。
- MarkItDown 本身同样使用 MIT License，版权归其原作者所有。

## English Summary

MarkItDown-Chinese is an unofficial Windows wrapper around Microsoft's open-source MarkItDown CLI. It adds a Chinese interactive workflow, drag-and-drop conversion, progress feedback, file-lock detection, and automatic output-name collision handling. A portable Windows release includes the Python runtime and dependencies, so end users do not need to install Python. It does not reimplement document conversion; all parsing is performed by MarkItDown. Optional lightweight AI hooks call Xiaomi-OCR-0 and Qwen3-TTS over HTTP; no PyTorch/Transformers are installed in the tool environment. This project is not affiliated with or endorsed by Microsoft. Licensed under MIT.
