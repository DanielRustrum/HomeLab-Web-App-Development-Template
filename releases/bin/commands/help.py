"""Help command for the nami CLI."""
from __future__ import annotations

import argparse
import sys


def register_help_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the `help` subcommand and its CLI arguments."""
    parser = subparsers.add_parser("help", help="Show help for a command.")
    parser.add_argument("topic", nargs="?", help="Command to show detailed help for.")


def run_help_command(args: argparse.Namespace) -> int:
    """Render general or command-specific help output."""
    root_parser = getattr(args, "_root_parser", None)
    if root_parser is None:
        print("nami: help is unavailable (parser not configured)", file=sys.stderr)
        return 1

    topic = args.topic
    if not topic:
        root_parser.print_help()
        print()
        print("Run 'nami help <command>' for detailed usage.")
        return 0

    subparsers_action = _find_subparsers_action(root_parser)
    if not subparsers_action or topic not in subparsers_action.choices:
        print(f"nami: unknown command '{topic}'", file=sys.stderr)
        root_parser.print_help()
        return 1

    subparsers_action.choices[topic].print_help()
    return 0


def _find_subparsers_action(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None
