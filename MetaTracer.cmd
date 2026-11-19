@echo off
REM MetaTracer app launcher (Windows). Double-click after install.cmd. TASK-56.
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo ERROR: virtualenv not found. Run install.cmd first.
  pause
  exit /b 1
)

"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\desktop.py" run %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" pause
exit /b %CODE%
