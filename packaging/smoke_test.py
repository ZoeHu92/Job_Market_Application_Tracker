"""Check a built release: its own Python imports everything and the app answers in a browser.

    python packaging/smoke_test.py dist/AcademicJobTracker
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def main(folder: str) -> int:
    root = Path(folder).resolve()
    exe = root / "python" / ("python.exe" if sys.platform.startswith("win") else "bin/python3")
    app = root / "app"
    subprocess.run([str(exe), "-c", "import streamlit, pandas, lxml, feedparser, yaml, openpyxl, tracker.scrape"],
                   cwd=app, check=True)
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "TRACKER_DATA_ROOT": tmp, "TRACKER_NO_AUTO_UPDATE": "1"}
        proc = subprocess.Popen([str(exe), "-m", "streamlit", "run", "app.py", "--server.port", "8765",
                                 "--server.headless", "true"], cwd=app, env=env)
        try:
            for _ in range(120):
                try:
                    body = urllib.request.urlopen("http://localhost:8765/_stcore/health", timeout=2).read()
                    page = urllib.request.urlopen("http://localhost:8765/", timeout=5).read()
                    print("health:", body.decode().strip(), "| page bytes:", len(page))
                    return 0
                except OSError:
                    time.sleep(1)
            print("app did not start")
            return 1
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
