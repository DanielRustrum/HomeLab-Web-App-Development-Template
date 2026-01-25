from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def register_dev_command(subparsers: argparse._SubParsersAction) -> None:
    dev_parser = subparsers.add_parser("dev", help="Run the template project in Docker.")
    dev_parser.add_argument("--no-build", action="store_true", help="Skip docker compose build.")


def run_dev_command(args: argparse.Namespace) -> int:
    compose_file = REPO_ROOT / "src" / "orchestrator" / "docker-compose.yaml"
    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "up",
        "-d",
    ]
    if not args.no_build:
        cmd.append("--build")

    result = subprocess.run(cmd, check=False, cwd=str(compose_file.parent))
    return result.returncode
