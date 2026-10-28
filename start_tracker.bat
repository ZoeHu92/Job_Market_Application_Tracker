@echo off
rem Windows: double-click to open the tracker in your browser.
cd /d "%~dp0"

rem Get the latest weekly job data and app updates (your statuses in my_data\ are never touched).
if exist .git (
  where git >nul 2>nul && git pull --ff-only --quiet
)

if not exist .venv\Scripts\python.exe (
  echo First run: setting up Python packages ^(about a minute^)...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist .venv\Scripts\python.exe (
    echo Python 3 is required: https://www.python.org/downloads/
    pause
    exit /b 1
  )
  .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
)
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

.venv\Scripts\python.exe -m streamlit run app.py
pause
