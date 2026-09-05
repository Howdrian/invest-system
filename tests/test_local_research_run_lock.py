"""OS-held lock survives exec, prevents overlap and releases after a crash."""
import os

import pytest

import subprocess
import sys
import time
from pathlib import Path


pytestmark = pytest.mark.skipif(os.name != "posix", reason="Mac/Linux deployment adapter")

LOCK_SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/with_local_research_lock.py'


def test_exec_lock_rejects_overlap_and_releases_after_exit(tmp_path):
    lock = tmp_path / 'research.lock'
    ready = tmp_path / 'ready'
    cmd = [sys.executable, str(LOCK_SCRIPT), str(lock), '--']
    child = subprocess.Popen(cmd + [sys.executable, '-c',
        'import pathlib,time; pathlib.Path(' + repr(str(ready)) + ').touch(); time.sleep(30)'])
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        blocked = subprocess.run(cmd + [sys.executable, '-c', 'raise SystemExit(0)'], capture_output=True, timeout=5)
        assert blocked.returncode == 75
        assert b'already active' in blocked.stderr
    finally:
        child.kill()
        child.wait(timeout=5)
    success = subprocess.run(cmd + [sys.executable, '-c', 'raise SystemExit(0)'], timeout=5)
    assert success.returncode == 0
    assert lock.exists()  # No unsafe stale-file deletion needed.
