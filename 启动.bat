@echo off
setlocal
cd /d "%~dp0"
set WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--disable-gpu --no-sandbox

set "PY="
if defined LULL_PYTHON set "PY=%LULL_PYTHON%"
if not defined PY if exist "%~dp0.venv\Scripts\pythonw.exe" set "PY=%~dp0.venv\Scripts\pythonw.exe"
if not defined PY if exist "C:\Users\jmsbs\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe" set "PY=C:\Users\jmsbs\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe"
if not defined PY for %%P in (pythonw.exe pyw.exe) do if not defined PY where %%P >nul 2>nul && set "PY=%%P"

if not defined PY (
  echo Python was not found. Install Python 3.13 or set LULL_PYTHON.
  pause
  exit /b 1
)

start "" "%PY%" "%~dp0launcher.py"
