"""Start the development workspace container and optional shell."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def register_workspace_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the `workspace` subcommand and its CLI arguments."""
    parser = subparsers.add_parser(
        "workspace",
        help="Start the workspace container for development.",
    )
    parser.add_argument("--no-build", action="store_true", help="Skip docker compose build.")
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Open an interactive shell in the workspace container after start.",
    )


def run_workspace_command(args: argparse.Namespace) -> int:
    """Bring up the workspace container and optionally open a shell."""
    compose_file = REPO_ROOT / "ops" / "docker" / "workspace.compose.yaml"
    cmd = [
        "docker",
        "compose",
        "--project-directory",
        str(REPO_ROOT),
        "-f",
        str(compose_file),
        "up",
        "-d",
    ]
    if not args.no_build:
        cmd.append("--build")

    result = subprocess.run(cmd, check=False, cwd=str(REPO_ROOT))
    if result.returncode != 0 or not args.shell:
        return result.returncode

    shell_cmd = [
        "docker",
        "compose",
        "--project-directory",
        str(REPO_ROOT),
        "-f",
        str(compose_file),
        "exec",
        "workspace",
        "bash",
    ]
    shell_result = subprocess.run(shell_cmd, check=False, cwd=str(REPO_ROOT))
    return shell_result.returncode
