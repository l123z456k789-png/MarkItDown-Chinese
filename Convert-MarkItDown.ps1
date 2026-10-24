param(
    [switch]$Prompt,
    [Parameter(Mandatory=$true, Position=0)]
    [string]$InputFile
)

$ErrorActionPreference = 'Continue'

$root     = $PSScriptRoot
$python   = Join-Path $root '.venv\Scripts\python.exe'
$outDir   = Join-Path $root 'output'
$interval = 4

function Exit-WithPrompt([int]$code) {
    if ($Prompt) {
        Write-Host ''
        Write-Host '按任意键关闭...'
    }
    exit $code
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Write-Host ('[错误] 找不到虚拟环境 Python：' + $python)
    Exit-WithPrompt 2
}

$src = $null
try { $src = Get-Item -LiteralPath $InputFile -ErrorAction Stop } catch { $src = $null }
if ($null -eq $src -or $src.PSIsContainer) {
    Write-Host ('[跳过] 不是有效文件：' + $InputFile)
    Exit-WithPrompt 3
}

$ext = [IO.Path]::GetExtension($src.Name).ToLowerInvariant()
if ($ext -eq '.doc') {
    Write-Host ''
    Write-Host '不支持的文件格式：.doc'
    Write-Host ''
    Write-Host 'Microsoft MarkItDown 0.1.7 不直接支持旧版 Word .doc。'
    Write-Host '请使用 Word 另存为 .docx 后重新转换。'
    Exit-WithPrompt 7
}
if ($ext -eq '.ppt') {
    Write-Host ''
    Write-Host '不支持的文件格式：.ppt'
    Write-Host ''
    Write-Host 'Microsoft MarkItDown 0.1.7 不直接支持旧版 PowerPoint .ppt。'
    Write-Host '请使用 PowerPoint 另存为 .pptx 后重新转换。'
    Exit-WithPrompt 7
}

$fs = $null
try {
    $fs = [IO.File]::Open($src.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
} catch [System.IO.IOException] {
    Write-Host ''
    Write-Host '无法读取文件。'
    Write-Host '该文件可能正在被 Word / Excel / PowerPoint 等程序占用。'
    Write-Host '请保存并关闭文件后重试。'
    Write-Host ''
    Write-Host ('原始错误：' + $_.Exception.Message)
    Exit-WithPrompt 6
} catch [System.UnauthorizedAccessException] {
    Write-Host ''
    Write-Host '无法读取文件。'
    Write-Host '该文件可能正在被 Word / Excel / PowerPoint 等程序占用。'
    Write-Host '请保存并关闭文件后重试。'
    Write-Host ''
    Write-Host ('原始错误：' + $_.Exception.Message)
    Exit-WithPrompt 6
} catch {
    Write-Host ''
    Write-Host '无法打开文件。'
    Write-Host ('原始错误：' + $_.Exception.Message)
    Exit-WithPrompt 6
} finally {
    if ($null -ne $fs) { $fs.Close(); $fs.Dispose() }
}

if (-not (Test-Path -LiteralPath $outDir -PathType Container)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}

$baseName = [IO.Path]::GetFileNameWithoutExtension($src.Name)
if ([string]::IsNullOrWhiteSpace($baseName)) { $baseName = $src.Name }

$outPath = Join-Path $outDir ($baseName + '.md')
$n = 2
while (Test-Path -LiteralPath $outPath) {
    if ($n -gt 9999) {
        Write-Host '[错误] 同名输出文件过多，已停止。'
        Exit-WithPrompt 4
    }
    $outPath = Join-Path $outDir ($baseName + '_' + $n + '.md')
    $n++
}

Write-Host '========================================'
Write-Host 'MarkItDown'
Write-Host ('输入文件：' + $src.FullName)
Write-Host ('输出文件：' + $outPath)
Write-Host '========================================'
Write-Host ''
Write-Host '正在转换，请勿关闭窗口...'
Write-Host ''

$argLine = '-m markitdown "' + $src.FullName + '" -o "' + $outPath + '"'
$sw = [Diagnostics.Stopwatch]::StartNew()
$psi = New-Object Diagnostics.ProcessStartInfo
$psi.FileName = $python
$psi.Arguments = $argLine
$psi.UseShellExecute = $false
$psi.WorkingDirectory = $root
$psi.RedirectStandardError = $true
$proc = $null
$errTask = $null
try {
    $proc = [Diagnostics.Process]::Start($psi)
    $errTask = $proc.StandardError.ReadToEndAsync()
} catch {
    $sw.Stop()
    Write-Host '[错误] 无法启动 MarkItDown 进程。'
    Write-Host $_.Exception.Message
    Exit-WithPrompt 5
}

Write-Host ('[' + (Get-Date -Format 'HH:mm:ss') + '] 正在转换，已运行 0 秒')
$nextBeat = (Get-Date).AddSeconds($interval)
while (-not $proc.WaitForExit(500)) {
    if ((Get-Date) -ge $nextBeat) {
        $elapsed = [int]$sw.Elapsed.TotalSeconds
        Write-Host ('[' + (Get-Date -Format 'HH:mm:ss') + '] 正在转换，已运行 ' + $elapsed + ' 秒')
        $nextBeat = (Get-Date).AddSeconds($interval)
    }
}
$proc.WaitForExit()
$sw.Stop()

$code = $proc.ExitCode
$secs = $sw.Elapsed.TotalSeconds.ToString('0.0')
$errText = ''
if ($null -ne $errTask) { $errText = [string]$errTask.Result }

if ($errText.Trim().Length -gt 0) {
    Write-Host ''
    Write-Host '--- MarkItDown 原始输出 ---'
    Write-Host $errText.TrimEnd()
}

Write-Host ''
if (($code -eq 0) -and (Test-Path -LiteralPath $outPath -PathType Leaf)) {
    Write-Host '转换完成'
    Write-Host ('耗时：' + $secs + ' 秒')
    Write-Host ('输出：' + $outPath)
    Exit-WithPrompt 0
} else {
    Write-Host '转换失败'
    Write-Host ('退出码：' + $code)
    Write-Host '请查看上方错误信息'
    if ($errText -match 'UnsupportedFormatException') {
        Write-Host ''
        Write-Host '提示：'
        Write-Host 'MarkItDown 没有找到能够处理该文件的转换器。'
        Write-Host ''
        Write-Host '可能原因：'
        Write-Host '  1. 文件格式不受支持'
        Write-Host '  2. 扩展名和真实文件类型不一致'
        Write-Host '  3. 文件已损坏'
        Write-Host '  4. 文件使用特殊封装或保护'
        Write-Host ''
        Write-Host '输入 help 查看支持格式。'
    }
    Exit-WithPrompt 1
}
