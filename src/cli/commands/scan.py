"""Run template scanning/generation tasks (types, future generators, etc.)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ScanStep:
    name: str
    cmd: list[str]


def register_scan_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the `scan` subcommand and its CLI arguments."""
    parser = subparsers.add_parser(
        "scan",
        help="Run codegen tasks for a template folder.",
    )
    parser.add_argument(
        "--template",
        dest="template",
        default=None,
        help="Template folder path (default: <repo>/template).",
    )


def build_scan_steps(template_dir: Path) -> list[ScanStep]:
    """Build the list of scan steps to run for the given template."""
    routes_dir = template_dir / "routes"
    library_dir = template_dir / "library"
    types_out = library_dir / "api.types.ts"
    contracts_out = library_dir / "api.contracts.ts"

    gen_ts_types = REPO_ROOT / "src" / "orchestrator" / "gen_ts_types.py"
    return [
        ScanStep(
            name="gen_ts_types",
            cmd=[
                sys.executable,
                str(gen_ts_types),
                str(routes_dir),
                "--out",
                str(types_out),
                "--contracts-out",
                str(contracts_out),
            ],
        )
    ]


def run_scan_command(args: argparse.Namespace) -> int:
    """Run scan tasks based on parsed CLI args."""
    template_dir = Path(args.template).resolve() if args.template else (REPO_ROOT / "template")
    if not template_dir.exists():
        print(f"nami: template directory not found: {template_dir}", file=sys.stderr)
        return 1

    routes_dir = template_dir / "routes"
    if not routes_dir.exists():
        print(f"nami: routes directory not found: {routes_dir}", file=sys.stderr)
        return 1

    library_dir = template_dir / "library"
    library_dir.mkdir(parents=True, exist_ok=True)

    for step in build_scan_steps(template_dir):
        result = subprocess.run(step.cmd, check=False, cwd=str(REPO_ROOT))
        if result.returncode != 0:
            print(f"nami: scan step failed: {step.name}", file=sys.stderr)
            return result.returncode

    return 0
