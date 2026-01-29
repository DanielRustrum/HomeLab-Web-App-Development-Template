"""Run the development Docker compose stack for the template app."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DEV_PORT = 23541


def _resolve_dev_port(template_dir: str | None) -> int:
    """Resolve the port for the dev server URL."""
    if not template_dir:
        return DEFAULT_DEV_PORT

    template_path = Path(template_dir)
    if not template_path.is_absolute():
        template_path = REPO_ROOT / template_path

    for env_name in ("secret.env", "secrets.env"):
        env_path = template_path / env_name
        if not env_path.is_file():
            continue
        try:
            for raw_line in env_path.read_text().splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key == "APP_PORT":
                    return int(value)
                if key == "TSUNAMI_PORT":
                    return int(value)
        except OSError:
            return DEFAULT_DEV_PORT
        except ValueError:
            return DEFAULT_DEV_PORT

    return DEFAULT_DEV_PORT


def register_dev_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the `dev` subcommand and its CLI arguments."""
    dev_parser = subparsers.add_parser("dev", help="Run the template project in Docker.")
    dev_parser.add_argument("--no-build", action="store_true", help="Skip docker compose build.")
    dev_parser.add_argument("--template", help="Template directory for orchestrate mode.")
    dev_parser.add_argument("--temp-root", help="Temp root for compile/runtime folders.")
    dev_parser.add_argument("--force", action="store_true", help="Overwrite temp directories if they exist.")
    dev_parser.add_argument("--skip-build", action="store_true", help="Skip Vite build.")
    dev_parser.add_argument("--no-run", action="store_true", help="Do not start servers.")
    dev_parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop the dev Docker compose stack started by this command.",
    )


def run_dev_command(args: argparse.Namespace) -> int:
    """Launch the Docker compose stack, optionally forcing a rebuild."""
    if args.stop:
        compose_file = REPO_ROOT / "src" / "orchestrator" / "docker-compose.yaml"
        cmd = [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "down",
        ]
        result = subprocess.run(cmd, check=False, cwd=str(compose_file.parent))
        return result.returncode

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
    if result.returncode == 0:
        port = _resolve_dev_port(args.template)
        print(f"tsunami dev server: http://localhost:{port}", flush=True)
    return result.returncode
