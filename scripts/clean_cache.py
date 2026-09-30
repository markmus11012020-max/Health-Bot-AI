"""Recursively remove Python bytecode caches under the project root.

Usage:
    python scripts/clean_cache.py            # actually delete
    python scripts/clean_cache.py --dry-run  # only show what would be removed
    python scripts/clean_cache.py --root .   # custom project root (default: cwd)

Removes:
    - all ``__pycache__`` directories
    - all ``*.pyc`` / ``*.pyo`` files
    - all ``*.pyc`` orphans outside __pycache__ (just in case)

Skips (never touched):
    - ``venv/``, ``.venv/``, ``env/``
    - ``.git/``, ``.hg/``, ``.svn/``
    - ``node_modules/``
    - ``.streamlit/`` (Streamlit caches its own stuff; usually you want it kept)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Ensure emojis/symbols print correctly on Windows (default cp1251 console).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

EXCLUDE_DIRS = {
    "venv", ".venv", "env", ".env",
    ".git", ".hg", ".svn",
    "node_modules",
    ".streamlit",
    "build", "dist", ".eggs", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


def _is_excluded(path: Path, project_root: Path) -> bool:
    """Return True if `path` (or any of its parents up to project root) is excluded."""
    try:
        rel = path.relative_to(project_root).parts
    except ValueError:
        return True  # outside project root
    return any(part in EXCLUDE_DIRS for part in rel)


def collect_targets(project_root: Path) -> tuple[list[Path], list[Path]]:
    """Return (pycache_dirs, stray_pyc_files)."""
    pycache_dirs: list[Path] = []
    stray_pycs: list[Path] = []

    for p in project_root.rglob("__pycache__"):
        if not p.is_dir():
            continue
        if _is_excluded(p, project_root):
            continue
        pycache_dirs.append(p)

    for ext in ("*.pyc", "*.pyo"):
        for p in project_root.rglob(ext):
            if _is_excluded(p, project_root):
                continue
            stray_pycs.append(p)

    return pycache_dirs, stray_pycs


def human_size(num_bytes: int) -> str:
    units = ("B", "KB", "MB", "GB")
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def dir_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove __pycache__ directories and .pyc/.pyo files from the project."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without touching anything",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.root).resolve()
    if not project_root.is_dir():
        print(f"❌ Root is not a directory: {project_root}", file=sys.stderr)
        return 2

    print(f"🔎 Scanning: {project_root}")
    pycache_dirs, stray_pycs = collect_targets(project_root)

    if not pycache_dirs and not stray_pycs:
        print("✨ Nothing to clean — project is already bytecode-free.")
        return 0

    total_dirs = len(pycache_dirs)
    total_pycs = len(stray_pycs)
    total_bytes = sum(dir_size(d) for d in pycache_dirs) + sum(
        p.stat().st_size for p in stray_pycs if p.exists()
    )

    print(f"   Found: {total_dirs} __pycache__/ + {total_pycs} stray .pyc/.pyo "
          f"(~{human_size(total_bytes)})")

    if args.dry_run:
        print("\n-- DRY RUN — nothing will be deleted --")
        for d in pycache_dirs:
            print(f"  [dir ] {d.relative_to(project_root)}")
        for p in stray_pycs:
            print(f"  [file] {p.relative_to(project_root)}")
        print(f"\nWould free ~{human_size(total_bytes)}.")
        return 0

    removed_dirs = 0
    removed_files = 0
    for d in pycache_dirs:
        try:
            shutil.rmtree(d)
            removed_dirs += 1
        except OSError as exc:
            print(f"  ⚠️  failed to remove {d}: {exc}", file=sys.stderr)

    for p in stray_pycs:
        try:
            p.unlink()
            removed_files += 1
        except FileNotFoundError:
            # Already gone — it lived inside a __pycache__ we just rmtree'd.
            pass
        except OSError as exc:
            print(f"  ⚠️  failed to remove {p}: {exc}", file=sys.stderr)

    print(f"✅ Done. Removed {removed_dirs} directories and {removed_files} files.")
    print(f"   Freed ~{human_size(total_bytes)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
