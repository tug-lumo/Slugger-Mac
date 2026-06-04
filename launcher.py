"""
Entry point for PyInstaller .app bundle.
Starts the Streamlit server on all interfaces and shows a menu bar icon.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Explicit imports so PyInstaller's analysis compiles these into the archive.
import approach_config    # noqa: F401
import screenplay_parser  # noqa: F401
import vp_heuristics      # noqa: F401
import exporter           # noqa: F401
import project_state      # noqa: F401


def _resource(relative: str) -> str:
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.dirname(__file__), relative)


def _local_ip() -> str:
    for iface in ('en0', 'en1', 'en2'):
        try:
            r = subprocess.run(['ipconfig', 'getifaddr', iface],
                               capture_output=True, text=True, timeout=2)
            ip = r.stdout.strip()
            if ip:
                return ip
        except Exception:
            pass
    return 'unknown'


def _bonjour_host() -> str:
    try:
        r = subprocess.run(['scutil', '--get', 'LocalHostName'],
                           capture_output=True, text=True, timeout=2)
        name = r.stdout.strip()
        if name:
            return f'{name}.local'
    except Exception:
        pass
    return ''


def _external_ip() -> str:
    try:
        r = subprocess.run(['curl', '-s', '--max-time', '5', 'https://ifconfig.me'],
                           capture_output=True, text=True, timeout=7)
        return r.stdout.strip() or 'unavailable'
    except Exception:
        return 'unavailable'


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def _run_streamlit() -> None:
    # Streamlit registers signal handlers which only works on the main thread.
    # Suppress those calls — rumps owns the main thread and handles quit.
    import signal as _sig
    _orig_signal = _sig.signal
    def _noop_signal(sig, handler):
        if threading.current_thread() is threading.main_thread():
            return _orig_signal(sig, handler)
    _sig.signal = _noop_signal

    from streamlit.web import cli as stcli
    sys.argv = [
        'streamlit', 'run',
        _resource('app.py'),
        '--server.address=0.0.0.0',
        '--server.port=8501',
        '--server.headless=true',
        '--browser.gatherUsageStats=false',
    ]
    try:
        stcli.main()
    except SystemExit:
        pass


class SluggerMenuBar:
    def __init__(self, local_ip: str, external_ip: str, bonjour: str) -> None:
        import rumps
        self._app = rumps.App('⚾', quit_button=None)

        local_url    = 'http://localhost:8501'
        bonjour_url  = f'http://{bonjour}:8501' if bonjour else None
        network_url  = f'http://{local_ip}:8501'
        external_url = f'http://{external_ip}:8501' if external_ip != 'unavailable' else None

        def _open(_):            webbrowser.open(local_url)
        def _open_bonjour(_):    webbrowser.open(bonjour_url)
        def _open_network(_):    webbrowser.open(network_url)

        items = [
            rumps.MenuItem('Open Browser', callback=_open),
            None,
            rumps.MenuItem(f'Local      {local_url}',   callback=_open),
        ]
        if bonjour_url:
            items.append(rumps.MenuItem(f'LAN        {bonjour_url}', callback=_open_bonjour))
        items.append(rumps.MenuItem(f'Network    {network_url}', callback=_open_network))
        if external_url:
            items.append(rumps.MenuItem(f'External   {external_url}'))
        items += [
            None,
            rumps.MenuItem('Quit Slugger', callback=self._quit),
        ]
        self._app.menu = items

    def _quit(self, _) -> None:
        import rumps
        rumps.quit_application()

    def run(self) -> None:
        self._app.run()


if __name__ == '__main__':
    local_ip = _local_ip()

    bonjour    = _bonjour_host()
    already_running = _port_in_use(8501)

    if not already_running:
        credentials = Path.home() / '.streamlit' / 'credentials.toml'
        if not credentials.exists():
            credentials.parent.mkdir(parents=True, exist_ok=True)
            credentials.write_text('[general]\nemail = ""\n')

        threading.Thread(target=_run_streamlit, daemon=True).start()

        # Wait for server to be ready (up to 15 s)
        for _ in range(30):
            if _port_in_use(8501):
                break
            time.sleep(0.5)

        webbrowser.open('http://localhost:8501')

    else:
        # Already running — just surface the browser
        webbrowser.open('http://localhost:8501')

    # Fetch external IP (can be slow — do after server is up)
    external_ip = _external_ip()

    # Menu bar runs on the main thread until the user clicks Quit
    SluggerMenuBar(local_ip, external_ip, bonjour).run()
