"""CLI wrapper for the template orchestrator pipeline."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def register_orchestrate_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the `orchestrate` subcommand and its CLI arguments."""
    parser = subparsers.add_parser("orchestrate", help="Compile templates and run runtime servers.")
    parser.add_argument("--template", help="Template directory.")
    parser.add_argument("--temp-root", help="Temp root for compile/runtime folders.")
    parser.add_argument("--force", action="store_true", help="Overwrite temp directories if they exist.")
    parser.add_argument("--skip-build", action="store_true", help="Skip Vite build.")
    parser.add_argument("--no-run", action="store_true", help="Do not start servers.")


def run_orchestrate_command(args: argparse.Namespace) -> int:
    """Invoke the orchestrator with CLI-selected options."""
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
