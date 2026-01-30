"""Run the development Docker compose stack for the template app."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DEV_PORT = 8080


def _resolve_dev_port(template_dir: str | None) -> int:
    """Resolve the port for the dev server URL."""
    if not template_dir:
        return DEFAULT_DEV_PORT

    template_path = resolve_template_dir(Path(template_dir))
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


def resolve_template_dir(raw_template: Path) -> Path:
    """Allow passing the parent template dir by resolving template/app."""
    app_dir = raw_template / "app"
    if app_dir.is_dir() and not (raw_template / "routes").exists():
        return app_dir
    return raw_template


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
    ]
    override_path = None
    resolved_port = None
    if args.template:
        template_dir = resolve_template_dir(Path(args.template).expanduser())
        if not template_dir.is_absolute():
            template_dir = (Path.cwd() / template_dir).resolve()
        if not template_dir.exists():
            print(f"nami: template directory not found: {template_dir}", file=sys.stderr)
            return 1
        port = _resolve_dev_port(str(template_dir))
        resolved_port = port
        override_contents = "\n".join(
            [
                "services:",
                "  orchestrator:",
                "    environment:",
                f"      APP_PORT: \"{port}\"",
                "    volumes:",
                f"      - {template_dir}:/app/template",
                "    ports:",
                f"      - \"{port}:{port}\"",
                "    command: [\"python\", \"-u\", \"-m\", \"orchestrator.main\", \"--force\", \"--watch\", \"--template\", \"/app/template\"]",
                "",
            ]
        )
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(override_contents)
            override_path = handle.name
        cmd.extend(["-f", override_path])
    cmd.extend(["up", "-d"])
    if not args.no_build:
        cmd.append("--build")

    result = subprocess.run(cmd, check=False, cwd=str(compose_file.parent))
    if override_path:
        try:
            os.unlink(override_path)
        except OSError:
            pass
    if result.returncode == 0:
        port = resolved_port if resolved_port is not None else _resolve_dev_port(args.template)
        print(f"tsunami dev server: http://localhost:{port}", flush=True)
    return result.returncode
