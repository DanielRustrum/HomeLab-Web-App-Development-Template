#!/usr/bin/env python3
"""CLI entrypoint for project generation and orchestration helpers."""
from __future__ import annotations

import argparse
import sys

from commands.dev import register_dev_command, run_dev_command
from commands.help import register_help_command, run_help_command
from commands.init import register_init_command, run_init_command
from commands.install import register_install_command, run_install_command
from commands.scan import register_scan_command, run_scan_command
from commands.workspace import register_workspace_command, run_workspace_command


def build_parser() -> argparse.ArgumentParser:
    """Create the root argparse parser and register subcommands."""
    parser = argparse.ArgumentParser(prog="nami", description="Generate a project from /template.")
    parser.set_defaults(_root_parser=parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_init_command(subparsers)
    register_dev_command(subparsers)
    register_install_command(subparsers)
    register_scan_command(subparsers)
    register_workspace_command(subparsers)
    register_help_command(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch the selected subcommand and normalize exit codes."""
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
    if args.command == "install":
        try:
            return run_install_command(args)
        except Exception as exc:
            print(f"nami: {exc}", file=sys.stderr)
            return 1
    if args.command == "scan":
        try:
            return run_scan_command(args)
        except Exception as exc:
            print(f"nami: {exc}", file=sys.stderr)
            return 1
    if args.command == "workspace":
        try:
            return run_workspace_command(args)
        except Exception as exc:
            print(f"nami: {exc}", file=sys.stderr)
            return 1
    if args.command == "help":
        return run_help_command(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
