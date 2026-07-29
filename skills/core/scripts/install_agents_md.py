#!/usr/bin/env python3
"""Install mycelium's contract section into a repo's AGENTS.md.

Claude Code learns the mycelium protocol from the plugin: skills provide the
workflows, hooks enforce the post-action discipline. Codex has neither — what
it reads is `AGENTS.md`. So for a repo to behave the same under both agents,
the protocol has to exist as text in AGENTS.md, not only as plugin machinery.

This script installs that text between HTML-comment markers so it can be
updated in place when mycelium changes, without disturbing anything else in
the file.

It also writes `.living/mycelium-root`, a one-line file holding the absolute
path of this mycelium install. AGENTS.md is committed and shared, so it must
not contain machine-specific paths; it resolves the helper scripts through
this pointer instead, and the pointer is gitignored so each machine keeps its
own.

Usage:
    python install_agents_md.py [--target-dir PATH] [--check]
"""

import argparse
import sys
from pathlib import Path

BEGIN = "<!-- mycelium:begin — managed by install_agents_md.py, edits are overwritten -->"
END = "<!-- mycelium:end -->"

ROOT_POINTER = ".living/mycelium-root"


def mycelium_root() -> Path:
    """Repo root of this mycelium install (scripts/ -> core/ -> skills/ -> root)."""
    return Path(__file__).resolve().parent.parent.parent.parent


def load_template(root: Path) -> str:
    template = root / "skills" / "core" / "templates" / "agents-md-mycelium.md"
    if not template.exists():
        raise FileNotFoundError(f"Missing template: {template}")
    return template.read_text(encoding="utf-8").strip()


def render_block(root: Path) -> str:
    return f"{BEGIN}\n\n{load_template(root)}\n\n{END}"


def splice(existing: str, block: str) -> str:
    """Insert or replace the managed block, preserving everything around it.

    An unterminated BEGIN marker (someone deleted the END by hand) would
    otherwise swallow the rest of the file, so that case appends a fresh
    block rather than guessing where the old one ended.
    """
    start = existing.find(BEGIN)
    if start != -1:
        end = existing.find(END, start)
        if end != -1:
            return existing[:start] + block + existing[end + len(END) :]
    body = existing.rstrip("\n")
    return f"{body}\n\n{block}\n" if body else f"{block}\n"


def has_unmanaged_living_section(existing: str) -> bool:
    """Detect a hand-written `.living/` section outside the managed block.

    Warned about rather than merged: a repo that documented `.living/` in its
    own words may have said something more specific than the template, and
    silently ending up with two descriptions of the same protocol is exactly
    the drift mycelium exists to prevent.
    """
    outside = existing
    start = outside.find(BEGIN)
    if start != -1:
        end = outside.find(END, start)
        if end != -1:
            outside = outside[:start] + outside[end + len(END) :]
    return ".living/" in outside


def write_root_pointer(target_dir: Path, root: Path) -> bool:
    """Point the repo at this mycelium install. Returns True if it changed."""
    pointer = target_dir / ROOT_POINTER
    content = f"{root}\n"
    if pointer.exists() and pointer.read_text(encoding="utf-8") == content:
        return False
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(content, encoding="utf-8")
    return True


def ensure_pointer_ignored(target_dir: Path) -> bool:
    """Keep the machine-specific pointer out of git. Returns True if changed."""
    gitignore = target_dir / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if ROOT_POINTER in existing:
        return False
    block = f"\n# Mycelium install path for this machine (local only)\n{ROOT_POINTER}\n"
    gitignore.write_text(existing.rstrip("\n") + "\n" + block, encoding="utf-8")
    return True


def check(target_dir: Path, root: Path) -> int:
    agents = target_dir / "AGENTS.md"
    block = render_block(root)
    problems = []

    if not agents.exists():
        problems.append("AGENTS.md: missing")
    else:
        existing = agents.read_text(encoding="utf-8")
        if BEGIN not in existing:
            problems.append("AGENTS.md: mycelium section not installed")
        elif splice(existing, block) != existing:
            problems.append("AGENTS.md: mycelium section is stale")

    pointer = target_dir / ROOT_POINTER
    if not pointer.exists():
        problems.append(f"{ROOT_POINTER}: missing")
    elif pointer.read_text(encoding="utf-8").strip() != str(root):
        problems.append(f"{ROOT_POINTER}: points elsewhere ({pointer.read_text().strip()})")

    for p in problems:
        print(f"  {p}")
    if problems:
        print("\nRun without --check to install.")
        return 1
    print("  AGENTS.md and mycelium-root are current")
    return 0


def install(target_dir: Path, root: Path) -> int:
    agents = target_dir / "AGENTS.md"
    block = render_block(root)
    existing = agents.read_text(encoding="utf-8") if agents.exists() else ""

    if existing and BEGIN not in existing and has_unmanaged_living_section(existing):
        print(
            "  Note: AGENTS.md already describes .living/ in its own words.\n"
            "        The managed block is appended alongside it — reconcile the two\n"
            "        by hand so the repo has one description of the protocol, not two."
        )

    updated = splice(existing, block)
    if not existing:
        updated = f"# Agent instructions\n\n{updated}"
    if updated != existing:
        agents.write_text(updated, encoding="utf-8")
        print(f"  {'Updated' if existing else 'Created'}: AGENTS.md")
    else:
        print("  Unchanged: AGENTS.md")

    if write_root_pointer(target_dir, root):
        print(f"  Wrote: {ROOT_POINTER} -> {root}")
    else:
        print(f"  Unchanged: {ROOT_POINTER}")

    if ensure_pointer_ignored(target_dir):
        print(f"  Updated: .gitignore to ignore {ROOT_POINTER}")
    return 0


def parse_args():
    parser = argparse.ArgumentParser(
        description="Install mycelium's contract section into a repo's AGENTS.md."
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=Path.cwd(),
        help="Root of the repo to install into (default: current directory)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report drift without writing; exit 1 if missing or stale",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_dir = args.target_dir.resolve()
    root = mycelium_root()
    return check(target_dir, root) if args.check else install(target_dir, root)


if __name__ == "__main__":
    sys.exit(main())
