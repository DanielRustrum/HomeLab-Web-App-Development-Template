"""Start the development workspace container and optional shell."""
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


CLI_ROOT = Path(__file__).resolve().parents[1]


def register_workspace_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the `workspace` subcommand and its CLI arguments."""
    parser = subparsers.add_parser(
        "workspace",
        help="Start the workspace container for development.",
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Workspace directory to mount into the container (defaults to current directory).",
    )
    parser.add_argument("--no-build", action="store_true", help="Skip docker compose build.")
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="Skip installing Python/Node dependencies inside the workspace container.",
    )
    parser.add_argument("--no-python", action="store_true", help="Skip Python dependencies.")
    parser.add_argument("--no-node", action="store_true", help="Skip Node dependencies.")
    parser.add_argument(
        "--venv",
        default="/workspace/.venv",
        help="Virtualenv path inside the container (default: /workspace/.venv).",
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Open an interactive shell in the workspace container after start.",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop the workspace container and remove it.",
    )


def run_workspace_command(args: argparse.Namespace) -> int:
    """Bring up the workspace container and optionally open a shell."""
    workspace_root = Path(args.root).expanduser().resolve()
    if not workspace_root.exists():
        print(f"nami: workspace path not found: {workspace_root}")
        return 1

    compose_file = CLI_ROOT / "assets" / "workspace.compose.yaml"
    core_package_path = CLI_ROOT / "assets" / "core-package.json"
    core_package_json = core_package_path.read_text() if core_package_path.exists() else ""
    if args.stop:
        stop_cmd = [
            "docker",
            "compose",
            "--project-directory",
            str(CLI_ROOT),
            "-f",
            str(compose_file),
            "down",
        ]
        result = subprocess.run(stop_cmd, check=False, cwd=str(CLI_ROOT))
        return result.returncode

    cmd = [
        "docker",
        "compose",
        "--project-directory",
        str(CLI_ROOT),
        "-f",
        str(compose_file),
        "up",
        "-d",
    ]
    if not args.no_build:
        cmd.append("--build")

    env = os.environ.copy()
    env["NAMI_WORKSPACE_DIR"] = str(workspace_root)
    env["NAMI_CLI_DIR"] = str(CLI_ROOT)
    result = subprocess.run(cmd, check=False, cwd=str(CLI_ROOT), env=env)
    if result.returncode != 0:
        return result.returncode

    if not args.no_install:
        install_script = _build_install_script(args, core_package_json)
        install_cmd = [
            "docker",
            "compose",
            "--project-directory",
            str(CLI_ROOT),
            "-f",
            str(compose_file),
            "exec",
            "-T",
            "workspace",
            "bash",
            "-lc",
            install_script,
        ]
        install_result = subprocess.run(install_cmd, check=False, cwd=str(CLI_ROOT), env=env)
        if install_result.returncode != 0:
            return install_result.returncode

    if not args.shell:
        return 0

    shell_cmd = [
        "docker",
        "compose",
        "--project-directory",
        str(CLI_ROOT),
        "-f",
        str(compose_file),
        "exec",
        "workspace",
        "bash",
    ]
    shell_result = subprocess.run(shell_cmd, check=False, cwd=str(CLI_ROOT), env=env)
    return shell_result.returncode


def _build_install_script(args: argparse.Namespace, core_package_json: str) -> str:
    lines: list[str] = ["set -e"]
    if not args.no_python:
        venv_path = args.venv
        lines.extend(
            [
                f'VENV_PATH="{venv_path}"',
                'REQ_MAIN="/workspace/requirements.txt"',
                'REQ_BACKEND="/workspace/backend/requirements.txt"',
                'REQ_TEMPLATE="/workspace/template/app/requirements.txt"',
                'if [ -f "$REQ_MAIN" ] || [ -f "$REQ_BACKEND" ] || [ -f "$REQ_TEMPLATE" ]; then',
                '  mkdir -p "$(dirname "$VENV_PATH")"',
                '  if [ ! -d "$VENV_PATH" ]; then',
                '    python3 -m venv "$VENV_PATH"',
                "  fi",
                '  PY_EXE="$VENV_PATH/bin/python"',
                '  if [ ! -x "$PY_EXE" ]; then',
                '    echo "nami: virtualenv python not found: $PY_EXE" >&2',
                "    exit 1",
                "  fi",
                '  if [ -f "$REQ_MAIN" ]; then',
                '    "$PY_EXE" -m pip install -r "$REQ_MAIN"',
                "  fi",
                '  if [ -f "$REQ_BACKEND" ]; then',
                '    "$PY_EXE" -m pip install -r "$REQ_BACKEND"',
                "  fi",
                '  if [ -f "$REQ_TEMPLATE" ]; then',
                '    "$PY_EXE" -m pip install -r "$REQ_TEMPLATE"',
                "  fi",
                "fi",
            ]
        )
    if not args.no_node:
        lines.extend(
            [
                'HAS_NODE_DEPS() {',
                "  python3 - <<'PY' \"$1\"",
                "import json",
                "from pathlib import Path",
                "path = Path(__import__('sys').argv[1])",
                "if not path.is_file():",
                "    raise SystemExit(1)",
                "pkg = json.loads(path.read_text())",
                "deps = pkg.get('dependencies') or {}",
                "dev = pkg.get('devDependencies') or {}",
                "raise SystemExit(0 if (deps or dev) else 1)",
                "PY",
                "}",
                'if HAS_NODE_DEPS "/workspace/package.json"; then',
                "  (cd /workspace && npm install --package-lock=false)",
                "fi",
                'if HAS_NODE_DEPS "/workspace/frontend/package.json"; then',
                "  (cd /workspace/frontend && npm install --package-lock=false)",
                "fi",
                'if HAS_NODE_DEPS "/workspace/template/app/package.json"; then',
                "  (cd /workspace/template/app && npm install --package-lock=false)",
                "fi",
            ]
        )
        lines.extend(
            [
                'TS_MODULE_SRC="/workspace/src/ts_module"',
                'if [ ! -f "$TS_MODULE_SRC/package.json" ] && [ -f "/nami/ts_module/package.json" ]; then',
                '  TS_MODULE_SRC="/nami/ts_module"',
                "fi",
                'TS_MODULE_COPY="/workspace/.nami-ts_module"',
                'if [ -f "$TS_MODULE_SRC/package.json" ]; then',
                '  echo "nami: preparing ts_module from $TS_MODULE_SRC"',
                '  rm -rf "$TS_MODULE_COPY"',
                '  mkdir -p "$TS_MODULE_COPY"',
                '  cp -R "$TS_MODULE_SRC/." "$TS_MODULE_COPY/"',
                '  (cd "$TS_MODULE_COPY" && npm install --package-lock=false)',
                '  if command -v tsc >/dev/null 2>&1; then',
                '    (cd "$TS_MODULE_COPY" && npm run -s build)',
                "  else",
                '    (cd "$TS_MODULE_COPY" && npx -y -p typescript tsc -p tsconfig.json)',
                "  fi",
                "fi",
            ]
        )
        if core_package_json:
            lines.extend(
                [
                    'CORE_DIR="/workspace/.nami-core"',
                    'CORE_PKG="$CORE_DIR/package.json"',
                    "mkdir -p \"$CORE_DIR\"",
                    "cat > \"$CORE_PKG\" <<'JSON'",
                    core_package_json,
                    "JSON",
                    'if [ ! -d "/workspace/.nami-ts_module" ]; then',
                    '  echo "nami: ts_module not prepared; cannot install core deps" >&2',
                    "  exit 1",
                    "fi",
                    "npm install --no-save --package-lock=false --include=dev --prefix /workspace \"$CORE_DIR\"",
                ]
            )
    return "\n".join(lines)
