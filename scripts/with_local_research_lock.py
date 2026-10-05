#!/usr/bin/env python3
"""Mac/Linux local entry lock; execution remains in the existing daily runner."""
from __future__ import annotations

import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3 or args[1] != '--':
        print('Usage: with_local_research_lock.py LOCK_PATH -- COMMAND [ARGS]', file=sys.stderr)
        return 2
    path = Path(args[0])
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('A local research run is already active; not starting a duplicate.', file=sys.stderr)
            return 75
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps({'pid': os.getpid(), 'startedAt': datetime.now(timezone.utc).isoformat()}).encode())
        # The shell keeps this descriptor for the complete pipeline lifetime.
        # The OS releases the lock on process exit, including crashes; the
        # persistent metadata file is not itself a stale-lock condition.
        os.set_inheritable(fd, True)
        os.execvpe(args[2], args[2:], os.environ)
    finally:
        os.close(fd)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
