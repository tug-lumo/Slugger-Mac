#!/bin/bash
# serve.command — run Slugger as a local network server.
# Colleagues connect via http://<this-mac's-ip>:8501 in their browser.
# Double-click to start; close the terminal window to stop.

set -e
cd "$(dirname "$0")"

VENV_DIR="$(pwd)/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "Installing / checking dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Show the machine's local IP so colleagues know where to connect.
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "unknown")
echo ""
echo "====================================================="
echo "  Slugger is starting on the local network."
echo "  Connect from any device on this network:"
echo "  http://${LOCAL_IP}:8501"
echo "====================================================="
echo ""

streamlit run app.py \
    --server.address=0.0.0.0 \
    --server.port=8501 \
    --server.headless=true \
    --browser.gatherUsageStats=false
