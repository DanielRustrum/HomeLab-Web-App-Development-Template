"""Install Python and Node dependencies for a project."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def register_install_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the `install` subcommand and its CLI arguments."""
    parser = subparsers.add_parser(
        "install",
        help="Install Python and Node dependencies for a project.",
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Project root directory (defaults to current working directory).",
    )
    parser.add_argument("--no-python", action="store_true", help="Skip Python dependencies.")
    parser.add_argument("--no-node", action="store_true", help="Skip Node dependencies.")
    parser.add_argument("--venv", help="Virtualenv path to create/use (default: <root>/.venv).")


def run_install_command(args: argparse.Namespace) -> int:
    """Install dependencies based on detected manifests."""
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"nami: root not found: {root}", file=sys.stderr)
        return 1

    python_req_files = _find_python_requirements(root)
    node_dirs = _find_node_projects(root)

    if args.no_python:
        python_req_files = []
    if args.no_node:
        node_dirs = []

    if not python_req_files and not node_dirs:
        print("nami: no dependencies detected to install.")
        return 0

    if python_req_files:
        venv_path = Path(args.venv).resolve() if args.venv else root / ".venv"
        python_exe = _ensure_venv(venv_path)
        if python_exe is None:
            return 1
        for req_file in python_req_files:
            if _run([str(python_exe), "-m", "pip", "install", "-r", str(req_file)], cwd=root) != 0:
                return 1

    for node_dir in node_dirs:
        if _run(["npm", "install"], cwd=node_dir) != 0:
            return 1

    return 0


def _find_python_requirements(root: Path) -> list[Path]:
    candidates = [
        root / "requirements.txt",
        root / "backend" / "requirements.txt",
    ]
    return [path for path in candidates if path.is_file()]


def _find_node_projects(root: Path) -> list[Path]:
    candidates = [
        root,
        root / "frontend",
    ]
    results: list[Path] = []
    for path in candidates:
        if (path / "package.json").is_file():
            results.append(path)
    return results


def _ensure_venv(venv_path: Path) -> Path | None:
    if os.environ.get("VIRTUAL_ENV"):
        return Path(sys.executable)

    if not venv_path.exists():
        print(f"nami: creating virtualenv at {venv_path}")
        if _run([sys.executable, "-m", "venv", str(venv_path)], cwd=venv_path.parent) != 0:
            return None

    python_exe = venv_path / "bin" / "python"
    if not python_exe.exists():
        print(f"nami: virtualenv python not found: {python_exe}", file=sys.stderr)
        return None

    return python_exe


def _run(cmd: list[str], *, cwd: Path) -> int:
    return subprocess.run(cmd, check=False, cwd=str(cwd)).returncode
