"""Template orchestration: compile routes, build assets, and run servers."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VITE_PROJECT_DIR = REPO_ROOT / "src" / "orchestrator" / "vite"


def main(argv: list[str] | None = None) -> int:
    """Run the orchestration pipeline from CLI-style arguments."""
    parser = build_parser()
    args = parser.parse_args(argv)

    template_dir = Path(args.template).resolve()
    temp_root = resolve_temp_root(args.temp_root)
    temp_compile = temp_root / "tsunami_compile"
    runtime_root = temp_root / "tsunami_runtime"

    print(f"[orchestrator] template_dir={template_dir}", flush=True)
    print(f"[orchestrator] temp_compile={temp_compile}", flush=True)
    print(f"[orchestrator] runtime_root={runtime_root}", flush=True)

    prepare_dir(temp_compile, force=args.force)
    prepare_dir(runtime_root, force=args.force)

    stage_template(template_dir, temp_compile)
    print("[orchestrator] template staged", flush=True)

    if not args.skip_build:
        build_assets(temp_compile, runtime_root)
        print("[orchestrator] assets built", flush=True)

    assemble_runtime(temp_compile, runtime_root)
    print("[orchestrator] runtime assembled", flush=True)

    if args.no_run:
        return 0

    return run_servers(runtime_root)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for orchestrator settings."""
    parser = argparse.ArgumentParser(description="Orchestrate template compilation and runtime.")
    parser.add_argument("--template", default=str(REPO_ROOT / "template"), help="Template directory.")
    parser.add_argument(
        "--temp-root",
        default="/temp",
        help="Temp root for compile/runtime folders (falls back to /tmp).",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite temp directories if they exist.")
    parser.add_argument("--skip-build", action="store_true", help="Skip Vite build.")
    parser.add_argument("--no-run", action="store_true", help="Do not start servers.")
    return parser


def resolve_temp_root(raw: str) -> Path:
    """Resolve a temp root directory, falling back to /tmp."""
    candidate = Path(raw)
    if candidate.exists():
        return candidate
    fallback = Path("/tmp")
    return fallback if fallback.exists() else candidate


def prepare_dir(path: Path, *, force: bool) -> None:
    """Ensure a clean directory, optionally deleting an existing one."""
    if path.exists():
        if not force:
            raise FileExistsError(f"{path} already exists (use --force to overwrite)")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def stage_template(template_dir: Path, temp_compile: Path) -> None:
    """Copy the template tree into the compile staging area."""
    if not template_dir.exists():
        raise FileNotFoundError(f"Template directory not found: {template_dir}")

    shutil.copytree(template_dir, temp_compile / "template", dirs_exist_ok=True)


def build_assets(temp_compile: Path, runtime_root: Path) -> None:
    """Build Vite assets from template routes into the runtime directory."""
    template_dir = temp_compile / "template"
    routes_dir = template_dir / "routes"
    if not routes_dir.exists():
        print(f"[orchestrator] routes_dir missing: {routes_dir}", flush=True)
        return

    entries_dir = template_dir / "__entries__"
    build_route_entries(routes_dir, entries_dir, template_dir)
    entries_manifest = template_dir / "entries.json"
    if not entries_manifest.exists():
        raise RuntimeError(f"Missing entries manifest: {entries_manifest}")
    print(f"[orchestrator] entries_manifest={entries_manifest}", flush=True)

    env = os.environ.copy()
    env["VITE_ROOT"] = str(VITE_PROJECT_DIR)
    env["ROUTES_DIR"] = str(entries_dir)
    env["ROUTES_MANIFEST"] = str(entries_manifest)
    env["OUT_DIR"] = str(runtime_root / "assets")

    npm_cmd = ["npm", "install"]
    subprocess.run(npm_cmd, cwd=str(VITE_PROJECT_DIR), check=True, env=env)

    build_cmd = ["npm", "run", "build"]
    subprocess.run(build_cmd, cwd=str(VITE_PROJECT_DIR), check=True, env=env)


def build_route_entries(routes_dir: Path, entries_dir: Path, template_dir: Path) -> None:
    """Create Vite entrypoints for every route file."""
    if entries_dir.exists():
        shutil.rmtree(entries_dir)
    entries_dir.mkdir(parents=True, exist_ok=True)

    entry_dir = template_dir / "src"
    entry_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "shell.html").write_text(
        "\n".join(
            [
                "<!doctype html>",
                "<html lang=\"en\">",
                "  <head>",
                "    <meta charset=\"UTF-8\" />",
                "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />",
                "    <title>Tsunami Routes</title>",
                "  </head>",
                "  <body>",
                "    <div id=\"app\"></div>",
                "    <script type=\"module\" src=\"/src/shell.tsx\"></script>",
                "  </body>",
                "</html>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (entry_dir / "shell.tsx").write_text("export {};\n", encoding="utf-8")

    entries: dict[str, str] = {}

    for route_path in routes_dir.rglob("*.tsx"):
        rel_path = route_path.relative_to(routes_dir)
        dest = entries_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        import_path = os.path.relpath(route_path, dest.parent).replace(os.sep, "/")
        if not import_path.startswith("."):
            import_path = f"./{import_path}"
        dest.write_text(
            "\n".join(
                [
                    'import React from "react";',
                    'import { createRoot } from "react-dom/client";',
                    f'import Page from "{import_path}";',
                    "",
                    "const mount = document.getElementById(\"app\");",
                    "if (mount) {",
                    "  const root = createRoot(mount);",
                    "  root.render(React.createElement(Page));",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        entry_key = rel_path.as_posix().removesuffix(".tsx")
        entries[entry_key] = str(dest)

    (template_dir / "entries.json").write_text(
        json.dumps(entries, indent=2),
        encoding="utf-8",
    )


def assemble_runtime(temp_compile: Path, runtime_root: Path) -> None:
    """Assemble runtime layout with endpoints, pages, and assets."""
    template_dir = temp_compile / "template"

    routes_dir = template_dir / "routes"
    endpoint_dir = runtime_root / "endpoint"
    routing_dir = runtime_root / "routing"

    endpoint_dir.mkdir(parents=True, exist_ok=True)
    routing_dir.mkdir(parents=True, exist_ok=True)

    for route_path in routes_dir.rglob("*"):
        if not route_path.is_file():
            continue
        rel_path = route_path.relative_to(routes_dir)
        if route_path.suffix == ".py":
            dest = endpoint_dir / rel_path
        elif route_path.suffix == ".tsx":
            dest = routing_dir / rel_path
        else:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(route_path, dest)

    copy_tree(template_dir / "utils", runtime_root / "utils")

    init_src = template_dir / "init.py"
    if init_src.exists():
        shutil.copy2(init_src, runtime_root / "init.py")

    config_src = template_dir / "config.yaml"
    if config_src.exists():
        shutil.copy2(config_src, runtime_root / "config.yaml")


def run_servers(runtime_root: Path) -> int:
    """Launch the routing server with the prepared runtime environment."""
    env = os.environ.copy()
    env["TSUNAMI_ENDPOINT_DIR"] = "endpoint"
    env["TSUNAMI_ROUTING_DIR"] = "routing"
    env["TSUNAMI_ASSETS_DIR"] = "assets"
    env["TSUNAMI_INIT_PATH"] = "init.py"
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(REPO_ROOT / "src" / "python_module"),
            str(REPO_ROOT / "src"),
        ]
    )

    cmd = [sys.executable, "-m", "python_module.main"]
    process = subprocess.Popen(cmd, cwd=str(runtime_root), env=env)

    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return process.wait()


def copy_tree(src: Path, dst: Path) -> None:
    """Copy a directory tree if the source exists."""
    if not src.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
