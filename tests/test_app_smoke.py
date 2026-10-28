"""Run the Streamlit app headlessly on sample data (in a subprocess, with its own data folder)."""
import json
import os
import subprocess
import sys
import textwrap
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytest.importorskip("streamlit")


def test_app_renders_with_sample_data(tmp_path):
    from tests.sample_data import sample_rows
    from tracker.store import write_jobs

    (tmp_path / "data").mkdir()
    write_jobs(sample_rows(date.today()), tmp_path / "data" / "jobs.csv")
    (tmp_path / "data" / "scrape_report.json").write_text(json.dumps(
        {"run_date": date.today().isoformat(), "finished_at": "2099-01-01T00:00:00", "sources": []}))
    script = textwrap.dedent(f"""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file({str(ROOT / "app.py")!r}, default_timeout=90)
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        print({{m.label: m.value for m in at.metric}})
    """)
    env = {**os.environ, "TRACKER_DATA_ROOT": str(tmp_path), "TRACKER_NO_AUTO_UPDATE": "1"}
    out = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, out.stderr[-3000:]
    assert "'Open positions': '30'" in out.stdout
