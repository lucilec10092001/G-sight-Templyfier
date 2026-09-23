@echo off
setlocal
cd /d "%~dp0"
set "TEMPLYFIER_MODE=server"
if not defined TEMPLYFIER_DATA_DIR (
  echo IT configuration required: TEMPLYFIER_DATA_DIR is missing. See SERVER_DEPLOYMENT.md.
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo IT must install the reviewed dependencies first. See SERVER_DEPLOYMENT.md.
  exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless=true
