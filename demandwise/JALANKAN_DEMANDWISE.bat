@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment belum dibuat.
  echo Jalankan: py -m venv .venv
  echo Lalu: .venv\Scripts\activate
  echo Dan: pip install -r requirements.txt
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
streamlit run app.py
