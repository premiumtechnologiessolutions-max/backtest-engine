@echo off
setlocal
cd /d "%~dp0"
set "LAB_EXTRAS=."
if /i "%~1"=="--verify-gpu" set "LAB_EXTRAS=.[gpu]"
if not "%~1"=="" if /i not "%~1"=="--verify-gpu" (
  echo Usage: START_UNIFIED_LAB.bat [--verify-gpu]
  exit /b 2
)
if not exist ".venv-lab\Scripts\python.exe" (
  py -3.12 -m venv .venv-lab
  if errorlevel 1 goto error
)
".venv-lab\Scripts\python.exe" -m pip install -e "%LAB_EXTRAS%"
if errorlevel 1 goto error
if /i "%~1"=="--verify-gpu" goto verify_gpu
echo Open http://127.0.0.1:8766 in your browser.
".venv-lab\Scripts\python.exe" -m norisk_quant.lab_cli serve
if errorlevel 1 goto error
exit /b 0
:verify_gpu
set "LAB_GPU_SEED=%RANDOM%%RANDOM%"
set "LAB_GPU_REPORT=%TEMP%\NoRiskFX-GPU-Verification-%LAB_GPU_SEED%.json"
".venv-lab\Scripts\python.exe" -m norisk_quant.lab_cli synthetic-demo --backend opencl --seed %LAB_GPU_SEED% > "%LAB_GPU_REPORT%"
set "LAB_GPU_RESULT=%ERRORLEVEL%"
echo GPU verification report: "%LAB_GPU_REPORT%"
exit /b %LAB_GPU_RESULT%
:error
echo Setup or server failed. Python 3.12 and internet access for first install are required.
if /i not "%~1"=="--verify-gpu" pause
exit /b 1
