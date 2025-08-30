@echo off
REM Run MACATS multi-agent trading system (Windows)

cd /d %~dp0

IF NOT EXIST .venv (
    echo [setup] Creating virtual environment...
    py -m venv .venv
)

call .venv\Scripts\activate.bat

echo [setup] Upgrading pip...
python -m pip install --upgrade pip >nul

IF EXIST requirements.txt (
    echo [setup] Installing requirements.txt...
    pip install -r requirements.txt
)

IF EXIST requirements-dev.txt (
    echo [setup] Installing requirements-dev.txt...
    pip install -r requirements-dev.txt
)

echo [run] Starting MACATS...
python main.py