"""Run the development Docker compose stack for the template app."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def register_dev_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the `dev` subcommand and its CLI arguments."""
    dev_parser = subparsers.add_parser("dev", help="Run the template project in Docker.")
    dev_parser.add_argument("--no-build", action="store_true", help="Skip docker compose build.")
    dev_parser.add_argument(
        "--uncontained",
        action="store_true",
        help="Run the orchestrator pipeline outside of docker compose.",
    )
    dev_parser.add_argument("--template", help="Template directory for orchestrate mode.")
    dev_parser.add_argument("--temp-root", help="Temp root for compile/runtime folders.")
    dev_parser.add_argument("--force", action="store_true", help="Overwrite temp directories if they exist.")
    dev_parser.add_argument("--skip-build", action="store_true", help="Skip Vite build.")
    dev_parser.add_argument("--no-run", action="store_true", help="Do not start servers.")


def run_dev_command(args: argparse.Namespace) -> int:
    """Launch the Docker compose stack, optionally forcing a rebuild."""
    if args.uncontained:
        repo_root = Path(__file__).resolve().parents[3]
        src_root = repo_root / "src"
        if str(src_root) not in sys.path:
            sys.path.insert(0, str(src_root))

        from orchestrator.main import main as orchestrator_main

        argv: list[str] = []
        if args.template:
            argv += ["--template", args.template]
        if args.temp_root:
            argv += ["--temp-root", args.temp_root]
        if args.force:
            argv.append("--force")
        if args.skip_build:
            argv.append("--skip-build")
        if args.no_run:
            argv.append("--no-run")

        return orchestrator_main(argv)

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
