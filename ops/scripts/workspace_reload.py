#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from watchfiles import DefaultFilter, watch

ROOT = Path(os.environ.get("TS_WATCH_ROOT", "/app")).resolve()
API_DIR = ROOT / "src/backend/api"
DECL_DIR = ROOT / "src/backend/declarations"
OUT_FILE = ROOT / "src/frontend/src/api.types.ts"
GEN_SCRIPT = ROOT / "ops/scripts/gen_ts_types.py"

ALLOWED_METHODS = "get,post,put,patch"


class InputsFilter(DefaultFilter):
    def __call__(self, change, path: str) -> bool:
        p = path.replace("\\", "/")
        if "__pycache__" in p or p.endswith(".pyc"):
            return False
        if "/.git/" in p or "/node_modules/" in p:
            return False
        return p.endswith(".py") and (
            p.startswith(API_DIR.as_posix()) or p.startswith(DECL_DIR.as_posix())
        )


def gather_inputs() -> list[str]:
    inputs: list[str] = []
    if API_DIR.exists():
        inputs += [str(p) for p in sorted(API_DIR.glob("*.py"))]
    if DECL_DIR.exists():
        inputs += [str(p) for p in sorted(DECL_DIR.glob("*.py"))]
    return inputs


def run_gen() -> int:
    inputs = gather_inputs()
    print("\n[ts_watch] Generating TS types...")

    if not GEN_SCRIPT.exists():
        print(f"[ts_watch] ERROR: missing generator script: {GEN_SCRIPT}")
        return 2

    if not inputs:
        print("[ts_watch] No input files found (skipping).")
        return 0

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python3",
        str(GEN_SCRIPT),
        *inputs,
        "--out",
        str(OUT_FILE),
        "--allowed-methods",
        ALLOWED_METHODS,
    ]

    r = subprocess.run(cmd, cwd=str(ROOT), check=False)
    if r.returncode == 0:
        print(f"[ts_watch] OK -> {OUT_FILE}")
    else:
        print(f"[ts_watch] FAILED (exit {r.returncode})")
    return r.returncode


def main() -> int:
    watch_dirs = [d for d in [API_DIR, DECL_DIR] if d.exists()]
    if not watch_dirs:
        print("[ts_watch] ERROR: watch dirs missing.")
        print(f"Expected:\n  - {API_DIR}\n  - {DECL_DIR}")
        return 2

    run_gen()

    print("[ts_watch] Watching:")
    for d in watch_dirs:
        print("  -", d)

    for changes in watch(*map(str, watch_dirs), watch_filter=InputsFilter(), debounce=300):
        changed = sorted({p.replace("\\", "/") for (_c, p) in changes})
        print("\n[ts_watch] Change detected:")
        for p in changed:
            print("  -", p)

        run_gen()
        time.sleep(0.05)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
