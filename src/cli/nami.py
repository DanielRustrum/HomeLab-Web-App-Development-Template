#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from commands.dev import register_dev_command, run_dev_command
from commands.init import register_init_command, run_init_command
from commands.orchestrate import register_orchestrate_command, run_orchestrate_command
from commands.workspace import register_workspace_command, run_workspace_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nami", description="Generate a project from /template.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_init_command(subparsers)
    register_dev_command(subparsers)
    register_orchestrate_command(subparsers)
    register_workspace_command(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        try:
            return run_init_command(args)
        except Exception as exc:
            print(f"nami: {exc}", file=sys.stderr)
            return 1
    if args.command == "dev":
        try:
            return run_dev_command(args)
        except Exception as exc:
            print(f"nami: {exc}", file=sys.stderr)
            return 1
    if args.command == "orchestrate":
        try:
            return run_orchestrate_command(args)
        except Exception as exc:
            print(f"nami: {exc}", file=sys.stderr)
            return 1
    if args.command == "workspace":
        try:
            return run_workspace_command(args)
        except Exception as exc:
            print(f"nami: {exc}", file=sys.stderr)
            return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
