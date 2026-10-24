@echo off
setlocal EnableExtensions
title MarkItDown
set "ROOT=%~dp0"
set "PY=%ROOT%runtime\python.exe"

if exist "%PY%" goto ready

set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" goto missing

:ready
if not "%~1"=="" goto drag

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%Interactive-MarkItDown.ps1"
if errorlevel 1 pause
exit /b 0

:drag
:loop
if "%~1"=="" goto dragdone
set "PROMPTARG="
if "%~2"=="" set "PROMPTARG=-Prompt"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%Convert-MarkItDown.ps1" "%~f1" %PROMPTARG%
shift
goto loop

:dragdone
pause >nul
exit /b 0

:missing
echo.
echo [ERROR] MarkItDown runtime not found:
echo   %ROOT%runtime\python.exe
echo   %ROOT%.venv\Scripts\python.exe
echo.
echo Portable package: re-extract the release ZIP.
echo Source package: run these commands in this folder:
echo   python -m venv .venv
echo   .venv\Scripts\python.exe -m pip install "markitdown[all]"
echo.
pause
exit /b 1
