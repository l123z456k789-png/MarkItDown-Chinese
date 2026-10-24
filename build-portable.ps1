param(
    [string]$PythonHome = '',
    [string]$OutputDir = 'dist',
    [string]$AssetName = 'MarkItDown-Chinese-Portable-Windows.zip'
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$venvSite = Join-Path $root '.venv\Lib\site-packages'

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Missing .venv Python: $venvPython. Create it with: python -m venv .venv"
}
if (-not (Test-Path -LiteralPath (Join-Path $venvSite 'markitdown'))) {
    throw "markitdown is not installed in .venv. Run: .venv\Scripts\python.exe -m pip install -r requirements-portable.txt"
}

if (-not $PythonHome) {
    $PythonHome = (& $venvPython -c "import sys; print(sys.base_prefix)" 2>&1).Trim()
}
if (-not (Test-Path -LiteralPath $PythonHome -PathType Container)) {
    throw "PythonHome not found: $PythonHome"
}
if (-not (Test-Path -LiteralPath (Join-Path $PythonHome 'python.exe') -PathType Leaf)) {
    throw "python.exe not found in PythonHome: $PythonHome"
}

$outRoot = Join-Path $root $OutputDir
$bundle = Join-Path $outRoot 'MarkItDown-Chinese'
$runtime = Join-Path $bundle 'runtime'
$zipPath = Join-Path $outRoot $AssetName

if (Test-Path -LiteralPath $outRoot) {
    Remove-Item -LiteralPath $outRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $runtime -Force | Out-Null

function Copy-Tree {
    param(
        [string]$Source,
        [string]$Destination,
        [string[]]$ExcludeDirs = @()
    )
    if (-not (Test-Path -LiteralPath $Source)) { return }
    $roboArgs = @($Source, $Destination, '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:2', '/W:1')
    if ($ExcludeDirs.Count -gt 0) {
        $roboArgs += '/XD'
        $roboArgs += $ExcludeDirs
    }
    & robocopy @roboArgs | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed with exit code $LASTEXITCODE`: $Source -> $Destination"
    }
}

# Copy the Python interpreter and its runtime DLLs.
Get-ChildItem -LiteralPath $PythonHome -File -Filter 'python*.exe' | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $runtime -Force
}
Get-ChildItem -LiteralPath $PythonHome -File -Filter 'python3*.dll' | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $runtime -Force
}
Get-ChildItem -LiteralPath $PythonHome -File -Filter 'vcruntime*.dll' | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $runtime -Force
}
$license = Join-Path $PythonHome 'LICENSE.txt'
if (Test-Path -LiteralPath $license) {
    Copy-Item -LiteralPath $license -Destination $runtime -Force
}

Copy-Tree (Join-Path $PythonHome 'DLLs') (Join-Path $runtime 'DLLs')

$libExcludes = @(
    (Join-Path $PythonHome 'Lib\site-packages'),
    (Join-Path $PythonHome 'Lib\test'),
    (Join-Path $PythonHome 'Lib\idlelib'),
    (Join-Path $PythonHome 'Lib\turtledemo'),
    (Join-Path $PythonHome 'Lib\ensurepip'),
    (Join-Path $PythonHome 'Lib\venv')
)
Copy-Tree (Join-Path $PythonHome 'Lib') (Join-Path $runtime 'Lib') $libExcludes

$runtimeSite = Join-Path $runtime 'Lib\site-packages'
New-Item -ItemType Directory -Path $runtimeSite -Force | Out-Null
Copy-Tree $venvSite $runtimeSite

# Add a portable CLI shim so `markitdown` works in the interactive cli mode.
$cmdText = "@echo off`r`n`"%~dp0python.exe`" -m markitdown %*`r`n"
[IO.File]::WriteAllText((Join-Path $runtime 'markitdown.cmd'), $cmdText, [Text.Encoding]::ASCII)

$bundleFiles = @(
    'README.md',
    'LICENSE',
    'Interactive-MarkItDown.ps1',
    'Convert-MarkItDown.ps1'
)
foreach ($name in $bundleFiles) {
    $source = Join-Path $root $name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Missing bundle file: $source"
    }
    Copy-Item -LiteralPath $source -Destination $bundle -Force
}
Get-ChildItem -LiteralPath $root -File -Filter '*.bat' | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $bundle -Force
}

# Verify that the copied interpreter is relocatable and can import MarkItDown.
$runtimePython = Join-Path $runtime 'python.exe'
$prefix = (& $runtimePython -c "import sys; print(sys.prefix)" 2>&1).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Portable Python failed to start: $prefix"
}
$expectedPrefix = (Resolve-Path -LiteralPath $runtime).Path
if ($prefix.ToLowerInvariant() -ne $expectedPrefix.ToLowerInvariant()) {
    throw "Portable Python is not relocatable. sys.prefix=$prefix expected=$expectedPrefix"
}

$version = (& $runtimePython -c "import importlib.metadata; print(importlib.metadata.version('markitdown'))" 2>&1).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Portable runtime cannot import markitdown: $version"
}
& $runtimePython -m markitdown --help > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Portable markitdown CLI check failed with exit code $LASTEXITCODE"
}

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path $bundle -DestinationPath $zipPath -CompressionLevel Optimal
$zip = Get-Item -LiteralPath $zipPath
"PORTABLE_MARKITDOWN_VERSION=$version"
"PORTABLE_RUNTIME_PREFIX=$prefix"
"PORTABLE_ZIP=$($zip.FullName)"
"PORTABLE_ZIP_BYTES=$($zip.Length)"
"PORTABLE_ZIP_SHA256=$((Get-FileHash -LiteralPath $zip.FullName -Algorithm SHA256).Hash)"
