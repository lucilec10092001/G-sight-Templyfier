@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo First installation required. Run install_and_launch.bat first.
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m streamlit run app.py
