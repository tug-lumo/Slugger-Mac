"""
Entry point for PyInstaller .app bundle.
Starts the Streamlit server and opens the browser.
"""

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _resource(relative: str) -> str:
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.dirname(__file__), relative)


def _open_browser():
    time.sleep(3)
    webbrowser.open("http://localhost:8501")


if __name__ == "__main__":
    credentials = Path.home() / ".streamlit" / "credentials.toml"
    if not credentials.exists():
        credentials.parent.mkdir(parents=True, exist_ok=True)
        credentials.write_text('[general]\nemail = ""\n')

    threading.Thread(target=_open_browser, daemon=True).start()

    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run",
        _resource("app.py"),
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--server.port=8501",
    ]
    sys.exit(stcli.main())
