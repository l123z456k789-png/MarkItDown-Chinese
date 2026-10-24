$ErrorActionPreference = 'Continue'

$root    = $PSScriptRoot
$convert = Join-Path $root 'Convert-MarkItDown.ps1'
$psExe   = Join-Path $PSHOME 'powershell.exe'

function Get-InputPaths([string]$raw) {
    $s = $raw.Trim()
    if ($s.StartsWith('"')) {
        $ms = [regex]::Matches($s, '"([^"]+)"')
        if ($ms.Count -gt 0) {
            return @($ms | ForEach-Object { $_.Groups[1].Value })
        }
    }
    return @($s.Trim('"'))
}

function Show-Formats {
    Write-Host ''
    Write-Host '============== MarkItDown 0.1.7 支持格式（本机审计 + 实测） =============='
    Write-Host ''
    Write-Host '【直接支持】'
    Write-Host '  PDF                .pdf'
    Write-Host '  Word               .docx'
    Write-Host '  PowerPoint         .pptx'
    Write-Host '  Excel              .xlsx .xls'
    Write-Host '                     （.xls：转换器与 xlrd 依赖已确认，本轮无真实样本，未实测）'
    Write-Host '  HTML               .html .htm'
    Write-Host '  CSV                .csv'
    Write-Host '  JSON / XML / 文本   .json .xml .txt .md 等'
    Write-Host '                     （按纯文本读取，不做结构化解析）'
    Write-Host '  EPUB               .epub'
    Write-Host '  ZIP                .zip（逐个转换压缩包内文件）'
    Write-Host '  RSS / Atom         .rss .atom'
    Write-Host '  Jupyter Notebook   .ipynb'
    Write-Host ''
    Write-Host '【有条件支持】'
    Write-Host '  扫描版 PDF        PDF 能识别，但没有 OCR，纯图片扫描件可能没有正文'
    Write-Host '  图片              .jpg .jpeg .png'
    Write-Host '                     无 exiftool / OCR / LLM，实测输出为空文件'
    Write-Host '  音频              .wav .mp3 .m4a .mp4'
    Write-Host '                     需 ffmpeg（本机已有）+ 联网语音识别，未实测'
    Write-Host '  Outlook 邮件      .msg（转换器与依赖存在，无样本，未实测）'
    Write-Host '  网址              http(s)://...（需要联网；YouTube/Wikipedia/RSS 等专用转换器）'
    Write-Host ''
    Write-Host '【明确不支持】'
    Write-Host '  Word 旧格式        .doc'
    Write-Host '  PowerPoint 旧格式  .ppt'
    Write-Host '  OpenDocument       .odt .ods .odp'
    Write-Host '  RTF                .rtf'
    Write-Host '  图片               .gif .bmp .tiff'
    Write-Host ''
    Write-Host '注意：'
    Write-Host '  .doc ≠ .docx，.ppt ≠ .pptx'
    Write-Host '  旧格式请先用 Office 另存为新格式（.docx / .pptx）再转换。'
    Write-Host '  未列出的扩展名不会被提前拦截，会交给 MarkItDown 按文件内容尝试。'
    Write-Host '=========================================================================='
    Write-Host ''
}

Write-Host '============================================================'
Write-Host ' MarkItDown - Microsoft 0.1.7'
Write-Host '============================================================'
Write-Host ''
Write-Host '常用支持格式：'
Write-Host '  PDF        .pdf'
Write-Host '  Word       .docx'
Write-Host '  PowerPoint .pptx'
Write-Host '  Excel      .xlsx .xls'
Write-Host '  Web/Text   .html .htm .csv .json .xml'
Write-Host '  E-book     .epub'
Write-Host '  Archive    .zip'
Write-Host ''
Write-Host '输入 help 查看完整格式说明'
Write-Host '输入文件路径 = 转换（可把文件拖进本窗口）'
Write-Host '输入 cli     = 官方 MarkItDown CLI（exit 返回）'
Write-Host '输入 q       = 退出'
Write-Host ''
Write-Host '请输入文件路径，或者直接把文件拖到这个窗口：'
Write-Host ''

while ($true) {
    Write-Host '> ' -NoNewline
    $line = [Console]::ReadLine()
    if ($null -eq $line) { break }
    $line = $line.Trim()
    if ($line -eq '') { continue }

    $lower = $line.ToLowerInvariant()
    if (($lower -eq 'q') -or ($lower -eq 'quit') -or ($lower -eq 'exit')) { break }

    if (($lower -eq 'help') -or ($lower -eq 'formats')) {
        Show-Formats
        continue
    }

    if ($lower -eq 'cli') {
        $runtime = Join-Path $root 'runtime'
        if (Test-Path -LiteralPath (Join-Path $runtime 'python.exe') -PathType Leaf) {
            Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
            $env:PATH = $runtime + ';' + $env:PATH
        } else {
            $venv = Join-Path $root '.venv'
            $env:VIRTUAL_ENV = $venv
            $env:PATH = (Join-Path $venv 'Scripts') + ';' + $env:PATH
        }
        $env:PROMPT = '(markitdown) $P$G'
        Write-Host ''
        Write-Host '进入官方 MarkItDown CLI（运行环境已加入 PATH）。输入 exit 返回。'
        Write-Host ''
        & cmd.exe /k
        Write-Host ''
        Write-Host '------------------------------------------------------------'
        Write-Host '继续输入/拖入另一个文件：'
        Write-Host ''
        continue
    }

    foreach ($p in (Get-InputPaths $line)) {
        & $psExe -NoProfile -ExecutionPolicy Bypass -File $convert $p
    }

    Write-Host ''
    Write-Host '------------------------------------------------------------'
    Write-Host '继续输入/拖入另一个文件：'
    Write-Host ''
}

exit 0
