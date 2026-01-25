#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from watchfiles import watch, DefaultFilter

ROOT = (
    Path(os.environ.get("DEV_RELOAD_ROOT", "")).resolve()
    if os.environ.get("DEV_RELOAD_ROOT")
    else Path(__file__).resolve().parents[2]
)


class BackendFilter(DefaultFilter):
    def __call__(self, change, path: str) -> bool:
        p = path.replace("\\", "/")
        if "__pycache__" in p or p.endswith(".pyc"):
            return False
        if "/.git/" in p or "/node_modules/" in p:
            return False
        return p.endswith(".py")


def _start_process(cmd: List[str]) -> subprocess.Popen:
    if os.name == "nt":
        return subprocess.Popen(cmd, cwd=ROOT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    return subprocess.Popen(cmd, cwd=ROOT, preexec_fn=os.setsid)


def _stop_process(proc: Optional[subprocess.Popen], timeout_s: float = 5.0) -> None:
    if not proc or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            os.killpg(proc.pid, signal.SIGTERM)

        deadline = time.time() + timeout_s
        while time.time() < deadline and proc.poll() is None:
            time.sleep(0.05)

        if proc.poll() is None:
            if os.name == "nt":
                proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def main() -> int:
    if "--" not in sys.argv:
        print("Usage:\n  python3 ops/scripts/dev_reload.py -- <server command...>\n")
        return 2

    server_cmd = sys.argv[sys.argv.index("--") + 1 :]
    if not server_cmd:
        print("[dev_reload] No server command provided.")
        return 2

    watch_root = ROOT / "src/backend"
    if not watch_root.exists():
        print(f"[dev_reload] ERROR: watch directory does not exist: {watch_root}")
        print("[dev_reload] Tip: make sure your compose mounts the repo into /app (volumes: - .:/app).")
        return 2

    watch_dirs = [str(watch_root)]

    print(f"[dev_reload] Starting server: {' '.join(server_cmd)}")
    proc = _start_process(server_cmd)

    try:
        for changes in watch(*watch_dirs, watch_filter=BackendFilter(), debounce=300):
            changed_paths = [p.replace("\\", "/") for (_c, p) in changes]

            print("\n[dev_reload] Change detected:")
            for p in sorted(set(changed_paths)):
                print(f"  - {p}")

            _stop_process(proc)

            print(f"[dev_reload] Restarting server: {' '.join(server_cmd)}")
            proc = _start_process(server_cmd)

    except KeyboardInterrupt:
        print("\n[dev_reload] Stopping...")
    finally:
        _stop_process(proc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
