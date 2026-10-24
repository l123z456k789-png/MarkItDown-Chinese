@echo off
setlocal EnableExtensions
title MarkItDown

rem Keep this file ASCII-only and delegate to the existing Chinese entry.
rem The Chinese filename is discovered at runtime to avoid batch-file encoding issues.
set "ENTRY="
for %%F in ("%~dp0*MarkItDown.bat") do (
    if /I not "%%~nxF"=="start-markitdown.bat" set "ENTRY=%%~fF"
)

if not defined ENTRY (
    echo.
    echo [ERROR] MarkItDown entry script not found in:
    echo   %~dp0
    echo.
    pause
    exit /b 1
)

call "%ENTRY%" %*
exit /b %ERRORLEVEL%
