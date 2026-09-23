@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python is not installed or is unavailable in PATH.
  echo Install Python 3.10 or later, then run this file again. Tested with Python 3.13.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the Templyfier environment...
  py -3 -m venv .venv
  if errorlevel 1 exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
python -m streamlit run app.py
