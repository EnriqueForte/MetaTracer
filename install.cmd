@echo off
REM MetaTracer installer (Windows). Double-click or run from this folder. TASK-56.
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="
where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3.12 -c "import sys" >nul 2>&1 && set "PY=py -3.12"
  if not defined PY py -3.11 -c "import sys" >nul 2>&1 && set "PY=py -3.11"
  if not defined PY py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo ERROR: MetaTracer needs Python 3.11 or 3.12.
  echo Install: winget install Python.Python.3.12
  echo Then also: winget install OpenJS.NodeJS.LTS
  pause
  exit /b 1
)

%PY% "%~dp0scripts\desktop.py" install %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" pause
exit /b %CODE%
