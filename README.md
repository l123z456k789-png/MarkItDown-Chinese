# MarkItDown-Chinese | Windows 文档转换助手

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

- 扫描版 PDF：没有 OCR，纯图片扫描件可能提取不到正文。
- 图片 `.jpg .jpeg .png`：没有 exiftool / OCR / LLM 时，实测输出为空文件。
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

## 限制

- 仅支持 Windows，依赖 PowerShell 和 `.venv`。
- 不提供 OCR；扫描版 PDF 和图片可能没有可用文本。
- 不重新实现 MarkItDown 的解析能力，格式支持范围由上游决定。
- 本项目是社区工具，与 Microsoft 没有隶属或背书关系。

## 上游与许可

- 上游项目：[microsoft/markitdown](https://github.com/microsoft/markitdown)
- 本仓库不包含微软上游 MarkItDown 的源代码。
- 本项目使用 MIT License，版权归 `l123z456k789-png` 所有；详见 [LICENSE](LICENSE)。
- MarkItDown 本身同样使用 MIT License，版权归其原作者所有。

## English Summary

MarkItDown-Chinese is an unofficial Windows wrapper around Microsoft's open-source MarkItDown CLI. It adds a Chinese interactive workflow, drag-and-drop conversion, progress feedback, file-lock detection, and automatic output-name collision handling. A portable Windows release includes the Python runtime and dependencies, so end users do not need to install Python. It does not reimplement document conversion; all parsing is performed by MarkItDown. This project is not affiliated with or endorsed by Microsoft. Licensed under MIT.
