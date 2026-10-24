@echo off
setlocal EnableExtensions
title MarkItDown
set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "MD=%VENV%\Scripts\markitdown.exe"

if not exist "%MD%" goto missing

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
echo [ERROR] markitdown.exe not found:
echo   %MD%
echo.
echo Fix it by running these commands in this folder:
echo   python -m venv .venv
echo   .venv\Scripts\python.exe -m pip install "markitdown[all]"
echo.
pause
exit /b 1
