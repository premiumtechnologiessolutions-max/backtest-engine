@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-lab\Scripts\python.exe" (
  py -3.12 -m venv .venv-lab
  if errorlevel 1 goto error
)
".venv-lab\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto error
echo Open http://127.0.0.1:8766 in your browser.
".venv-lab\Scripts\python.exe" -m norisk_quant.lab_cli serve
if errorlevel 1 goto error
exit /b 0
:error
echo Setup or server failed. Python 3.12 and internet access for first install are required.
pause
exit /b 1
