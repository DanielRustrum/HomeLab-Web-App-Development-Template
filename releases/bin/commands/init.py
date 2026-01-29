"""Initialize a new project from the repository template."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


LOCAL_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "template"
REPO_ROOT = Path(__file__).resolve().parents[3]
FALLBACK_TEMPLATE_DIR = REPO_ROOT / "template"


def register_init_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the `init` subcommand and its CLI arguments."""
    init_parser = subparsers.add_parser("init", help="Copy the template into a destination directory.")
    init_parser.add_argument("dest", help="Destination directory.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing files.")


def run_init_command(args: argparse.Namespace) -> int:
    """Run the init workflow with parsed CLI arguments."""
    init_project(Path(args.dest), force=args.force)
    return 0


def copy_item(src: Path, dst: Path, *, force: bool) -> None:
    """Copy a file or directory, honoring the force-overwrite flag."""
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=force)
        return
    if dst.exists() and not force:
        raise FileExistsError(f"{dst} already exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def init_project(dest: Path, *, force: bool) -> None:
    """Create a new project directory populated with the template files."""
    template_dir = LOCAL_TEMPLATE_DIR if LOCAL_TEMPLATE_DIR.exists() else FALLBACK_TEMPLATE_DIR
    if not template_dir.exists():
        raise FileNotFoundError(f"Template directory not found: {template_dir}")

    if dest.exists():
        if dest.is_file():
            raise FileExistsError(f"Destination is a file: {dest}")
        if any(dest.iterdir()) and not force:
            raise FileExistsError(f"Destination not empty: {dest} (use --force to overwrite)")
    else:
        dest.mkdir(parents=True, exist_ok=True)

    for entry in template_dir.iterdir():
        copy_item(entry, dest / entry.name, force=force)
