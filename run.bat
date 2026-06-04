@echo off
cd /d "%~dp0"

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

echo Installing / updating dependencies...
venv\Scripts\pip install -r requirements.txt -q

echo.
echo ================================================================
echo   Screenplay Breakdown Tool
echo   Opening in your browser at http://localhost:8501
echo   Press Ctrl+C to stop the server.
echo ================================================================
echo.

venv\Scripts\streamlit run app.py --server.headless false --browser.gatherUsageStats false
