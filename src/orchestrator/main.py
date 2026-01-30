"""Template orchestration: compile routes, build assets, and run servers."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VITE_PROJECT_DIR = REPO_ROOT / "src" / "orchestrator" / "vite"
DEFAULT_TEMPLATE_DIR = REPO_ROOT / "template" / "app"


def main(argv: list[str] | None = None) -> int:
    """Run the orchestration pipeline from CLI-style arguments."""
    parser = build_parser()
    args = parser.parse_args(argv)

    template_dir = resolve_template_dir(Path(args.template).resolve())
    temp_root = resolve_temp_root(args.temp_root)
    temp_compile = temp_root / "tsunami_compile"
    runtime_root = temp_root / "tsunami_runtime"

    print(f"[orchestrator] template_dir={template_dir}", flush=True)
    print(f"[orchestrator] temp_compile={temp_compile}", flush=True)
    print(f"[orchestrator] runtime_root={runtime_root}", flush=True)

    prepare_dir(temp_compile, force=args.force)
    prepare_dir(runtime_root, force=args.force)

    if args.watch:
        return watch_orchestrator(
            template_dir=template_dir,
            temp_compile=temp_compile,
            runtime_root=runtime_root,
            args=args,
        )

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
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE_DIR), help="Template directory.")
    parser.add_argument(
        "--temp-root",
        default="/temp",
        help="Temp root for compile/runtime folders (falls back to /tmp).",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite temp directories if they exist.")
    parser.add_argument("--skip-build", action="store_true", help="Skip Vite build.")
    parser.add_argument("--no-run", action="store_true", help="Do not start servers.")
    parser.add_argument("--watch", action="store_true", help="Watch template files and sync changes.")
    parser.add_argument(
        "--watch-interval",
        type=float,
        default=0.5,
        help="Watch polling interval in seconds.",
    )
    return parser


def resolve_temp_root(raw: str) -> Path:
    """Resolve a temp root directory, falling back to /tmp."""
    candidate = Path(raw)
    if candidate.exists():
        return candidate
    fallback = Path("/tmp")
    return fallback if fallback.exists() else candidate


def resolve_template_dir(raw_template: Path) -> Path:
    """Allow passing the parent template dir by resolving template/app."""
    app_dir = raw_template / "app"
    if app_dir.is_dir() and not (raw_template / "routes").exists():
        return app_dir
    return raw_template


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
    env = build_runtime_env(runtime_root)
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


def watch_orchestrator(
    *,
    template_dir: Path,
    temp_compile: Path,
    runtime_root: Path,
    args: argparse.Namespace,
) -> int:
    """Watch template files, sync runtime, and rebuild assets incrementally."""
    stage_template(template_dir, temp_compile)
    print("[orchestrator] template staged", flush=True)

    sync_runtime(
        template_dir=template_dir,
        temp_compile=temp_compile,
        runtime_root=runtime_root,
    )
    print("[orchestrator] runtime assembled", flush=True)

    vite_process = None
    if not args.skip_build:
        vite_process = start_vite_watch(temp_compile, runtime_root)
        print("[orchestrator] assets watch started", flush=True)
        wait_for_manifest(runtime_root / "assets")

    server_process = None
    if not args.no_run:
        server_process = start_server(runtime_root)

    routes_snapshot, components_snapshot, utils_snapshot, misc_snapshot = snapshot_template(template_dir)
    return_code = 0
    try:
        while True:
            time.sleep(max(args.watch_interval, 0.1))
            new_routes, new_components, new_utils, new_misc = snapshot_template(template_dir)
            if (new_routes, new_components, new_utils, new_misc) == (
                routes_snapshot,
                components_snapshot,
                utils_snapshot,
                misc_snapshot,
            ):
                continue

            tsx_changed, tsx_set_changed = diff_tsx_changes(routes_snapshot, new_routes)
            sync_runtime(
                template_dir=template_dir,
                temp_compile=temp_compile,
                runtime_root=runtime_root,
            )

            if tsx_changed:
                build_route_entries(
                    temp_compile / "template" / "routes",
                    temp_compile / "template" / "__entries__",
                    temp_compile / "template",
                )

            if tsx_set_changed and not args.skip_build:
                if vite_process is not None:
                    stop_process(vite_process)
                vite_process = start_vite_watch(temp_compile, runtime_root)

            routes_snapshot, components_snapshot, utils_snapshot, misc_snapshot = (
                new_routes,
                new_components,
                new_utils,
                new_misc,
            )
            print("[orchestrator] changes synced", flush=True)
    except KeyboardInterrupt:
        return_code = 0
    finally:
        if server_process is not None:
            stop_process(server_process)
        if vite_process is not None:
            stop_process(vite_process)
    return return_code


def start_server(runtime_root: Path) -> subprocess.Popen[bytes]:
    """Start the routing server without blocking the caller."""
    env = build_runtime_env(runtime_root)
    cmd = [sys.executable, "-m", "python_module.main"]
    return subprocess.Popen(cmd, cwd=str(runtime_root), env=env)


def build_runtime_env(runtime_root: Path) -> dict[str, str]:
    """Build environment variables for the runtime server."""
    env = os.environ.copy()
    env["TSUNAMI_ENDPOINT_DIR"] = str(runtime_root / "endpoint")
    env["TSUNAMI_ROUTING_DIR"] = str(runtime_root / "routing")
    env["TSUNAMI_ASSETS_DIR"] = str(runtime_root / "assets")
    env["TSUNAMI_INIT_PATH"] = str(runtime_root / "init.py")
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(REPO_ROOT / "src" / "python_module"),
            str(REPO_ROOT / "src"),
        ]
    )
    return env


def start_vite_watch(temp_compile: Path, runtime_root: Path) -> subprocess.Popen[bytes]:
    """Start Vite in build watch mode for incremental asset rebuilds."""
    template_dir = temp_compile / "template"
    routes_dir = template_dir / "routes"
    entries_dir = template_dir / "__entries__"
    build_route_entries(routes_dir, entries_dir, template_dir)

    entries_manifest = template_dir / "entries.json"
    if not entries_manifest.exists():
        raise RuntimeError(f"Missing entries manifest: {entries_manifest}")

    env = os.environ.copy()
    env["VITE_ROOT"] = str(VITE_PROJECT_DIR)
    env["ROUTES_DIR"] = str(entries_dir)
    env["ROUTES_MANIFEST"] = str(entries_manifest)
    env["OUT_DIR"] = str(runtime_root / "assets")

    npm_cmd = ["npm", "install"]
    subprocess.run(npm_cmd, cwd=str(VITE_PROJECT_DIR), check=True, env=env)

    cmd = ["npm", "run", "build", "--", "--watch"]
    return subprocess.Popen(cmd, cwd=str(VITE_PROJECT_DIR), env=env)


def wait_for_manifest(assets_dir: Path, *, timeout: float = 30.0) -> None:
    """Wait briefly for the Vite manifest to appear in watch mode."""
    deadline = time.monotonic() + max(timeout, 0.0)
    manifest = assets_dir / "manifest.json"
    fallback = assets_dir / ".vite" / "manifest.json"
    while time.monotonic() < deadline:
        if manifest.exists() or fallback.exists():
            return
        time.sleep(0.25)


def snapshot_template(
    template_dir: Path,
) -> tuple[dict[str, int], dict[str, int], dict[str, int], dict[str, int]]:
    """Snapshot relevant template files by relative path and mtime."""
    routes_snapshot = snapshot_paths(template_dir / "routes", suffixes={".py", ".tsx"})
    components_snapshot = snapshot_paths(template_dir / "components", suffixes={".ts", ".tsx", ".css"})
    utils_snapshot = snapshot_paths(template_dir / "utils", suffixes=None)

    misc_snapshot: dict[str, int] = {}
    for name in ("init.py", "config.yaml"):
        path = template_dir / name
        if path.exists():
            try:
                misc_snapshot[name] = path.stat().st_mtime_ns
            except OSError:
                continue
    return routes_snapshot, components_snapshot, utils_snapshot, misc_snapshot


def snapshot_paths(root: Path, *, suffixes: set[str] | None) -> dict[str, int]:
    """Return {relative_path: mtime_ns} for files in root."""
    snapshot: dict[str, int] = {}
    if not root.exists():
        return snapshot
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if suffixes is not None and path.suffix not in suffixes:
            continue
        try:
            snapshot[path.relative_to(root).as_posix()] = path.stat().st_mtime_ns
        except OSError:
            continue
    return snapshot


def diff_tsx_changes(
    before: dict[str, int],
    after: dict[str, int],
) -> tuple[bool, bool]:
    """Return (tsx_changed, tsx_set_changed) based on route snapshots."""
    before_tsx = {k: v for k, v in before.items() if k.endswith(".tsx")}
    after_tsx = {k: v for k, v in after.items() if k.endswith(".tsx")}
    tsx_set_changed = set(before_tsx) != set(after_tsx)
    tsx_changed = tsx_set_changed or before_tsx != after_tsx
    return tsx_changed, tsx_set_changed


def sync_runtime(*, template_dir: Path, temp_compile: Path, runtime_root: Path) -> None:
    """Sync template files into runtime and compile staging."""
    template_routes = template_dir / "routes"
    compile_routes = temp_compile / "template" / "routes"

    sync_dir(template_routes, compile_routes, suffixes={".py", ".tsx"})
    sync_dir(template_routes, runtime_root / "endpoint", suffixes={".py"})
    sync_dir(template_routes, runtime_root / "routing", suffixes={".tsx"})

    sync_dir(
        template_dir / "components",
        temp_compile / "template" / "components",
        suffixes={".ts", ".tsx", ".css"},
    )

    sync_dir(template_dir / "utils", runtime_root / "utils", suffixes=None)

    sync_file(template_dir / "init.py", runtime_root / "init.py")
    sync_file(template_dir / "config.yaml", runtime_root / "config.yaml")


def sync_file(src: Path, dst: Path) -> None:
    """Copy a single file to dst or remove dst if src is missing."""
    if not src.exists():
        if dst.exists():
            dst.unlink()
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def sync_dir(src: Path, dst: Path, *, suffixes: set[str] | None) -> None:
    """Mirror src into dst, deleting files that no longer exist."""
    if not src.exists():
        if dst.exists():
            shutil.rmtree(dst)
        return

    src_files: set[str] = set()
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        if suffixes is not None and path.suffix not in suffixes:
            continue
        rel = path.relative_to(src).as_posix()
        src_files.add(rel)
        dest_path = dst / rel
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest_path)

    if not dst.exists():
        return

    for path in sorted(dst.rglob("*"), reverse=True):
        if path.is_file():
            rel = path.relative_to(dst).as_posix()
            if rel not in src_files:
                path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def stop_process(process: subprocess.Popen[bytes]) -> None:
    """Terminate a child process politely."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
