"""Start the tracker and open it in your browser (used by the double-click launchers).

    python launch.py

Picks a free port, starts the app, and opens the page once it answers. Close the
window (or press Ctrl+C) to quit.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent


def free_port(start: int = 8501) -> int:
    for port in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def open_when_ready(url: str, timeout: float = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url + "/_stcore/health", timeout=2)
            webbrowser.open(url)
            return
        except OSError:
            time.sleep(0.5)


def main() -> int:
    os.chdir(HERE)  # .streamlit/config.toml is read from the working directory
    port = free_port()
    url = f"http://localhost:{port}"
    print(f"Academic Job Market Tracker is starting at {url}\n"
          "Your browser will open by itself. Keep this window open while you use the tracker; "
          "close it to quit.\n", flush=True)
    threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    from streamlit.web import cli as stcli

    sys.argv = ["streamlit", "run", str(HERE / "app.py"), "--server.port", str(port),
                "--server.headless", "true", "--browser.gatherUsageStats", "false"]
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())
