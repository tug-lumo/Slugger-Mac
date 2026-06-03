#!/usr/bin/env bash
# Double-click this file in Finder to launch the app.
# First time only: open Terminal, run  chmod +x run.command  in this folder.

cd "$(dirname "$0")"

# Suppress Streamlit's first-run email prompt
mkdir -p "$HOME/.streamlit"
if [ ! -f "$HOME/.streamlit/credentials.toml" ]; then
    printf '[general]\nemail = ""\n' > "$HOME/.streamlit/credentials.toml"
fi

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Installing / updating dependencies..."
venv/bin/pip install -r requirements.txt -q

echo ""
echo "================================================================"
echo "  Screenplay Breakdown Tool"
echo "  Opening in your browser at http://localhost:8501"
echo "  Press Ctrl+C to stop the server."
echo "================================================================"
echo ""

venv/bin/streamlit run app.py --server.headless false --browser.gatherUsageStats false
