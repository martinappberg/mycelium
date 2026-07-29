#!/usr/bin/env python3
"""Report and repair mycelium drift across Claude Code and Codex.

An installed mycelium is not one thing. It is:

  1. this checkout            — where the HOOKS run from
  2. a Claude plugin cache    — where the /mycelium:* SKILLS load from, pinned
                                to a commit at install time
  3. generated Codex skills   — $CODEX_HOME/skills/mycelium-*, generated from
                                commands/*.md at install time
  4. per-repo wiring          — AGENTS.md block + .living/mycelium-root

They update independently and nothing warns when they disagree. That is a real
failure mode, not a hypothetical: a repo can run hooks from a checkout that is
several commits ahead of the skills the agent is actually reading, so a change
that was written, tested and merged does nothing in the repo it was written for.

This script prints all four in one place, flags the mismatches, and (without
--check) fixes the two it can fix. The Claude plugin it cannot: that needs
`claude plugin update` and a restart.

Usage:
    python3 sync_agents.py [--repo PATH] [--check]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

OK = "  ok      "
WARN = "  ACTION  "


def mycelium_root() -> Path:
    """Repo root of this mycelium install (scripts/ -> core/ -> skills/ -> root)."""
    return Path(__file__).resolve().parent.parent.parent.parent


def git(root: Path, *args: str) -> str:
    """Run git in `root`, returning stripped stdout ("" on any failure)."""
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except OSError:
        return ""


def report_install(root: Path) -> str:
    """Section 1: what this checkout is, and whether it's behind its remote."""
    print(f"\nMycelium install — {root}")
    head = git(root, "rev-parse", "HEAD")
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD") or "(detached)"
    if not head:
        print(f"{WARN}not a git checkout — cannot tell which version this is")
        return ""

    dirty = git(root, "status", "--porcelain")
    print(f"{OK}{branch} @ {head[:12]}{'  (uncommitted changes)' if dirty else ''}")

    upstream = git(root, "rev-parse", "--abbrev-ref", "@{upstream}")
    if not upstream:
        print(f"{WARN}no upstream branch — this checkout has no source to pull from")
        return head

    # A tracking ref can exist locally while the branch no longer exists (or
    # never existed) on the remote — e.g. after a clone whose origin URL was
    # repointed. "Behind by 0" then reads as "up to date", which is wrong and
    # exactly the kind of false all-clear this script exists to prevent.
    remote = upstream.split("/", 1)[0]
    if remote != "." and not git(root, "ls-remote", "--heads", remote, upstream.split("/", 1)[1]):
        print(f"{WARN}{upstream} does not exist on the remote — the local ref is stale")
        return head

    counts = git(root, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
    ahead, behind = (counts.split() + ["0", "0"])[:2] if counts else ("0", "0")
    if behind != "0" and ahead != "0":
        print(f"{WARN}diverged from {upstream}: {ahead} ahead, {behind} behind")
    elif behind != "0":
        print(f"{WARN}{behind} commit(s) behind {upstream} — run: git -C {root} pull")
    elif ahead != "0":
        print(f"{OK}{ahead} commit(s) ahead of {upstream} (unpushed)")
    else:
        print(f"{OK}up to date with {upstream}")
    return head


def report_claude(root: Path, head: str, plugins: Path | None = None) -> None:
    """Section 2: the Claude plugin cache, pinned at install time.

    This is the half that silently goes stale: hooks run from `root` and update
    the moment you pull, but skills stay on whatever commit was installed.

    `plugins` defaults to the real `~/.claude/plugins`; tests pass a fixture.
    """
    print("\nClaude Code")
    plugins = plugins or Path.home() / ".claude" / "plugins"
    installed = plugins / "installed_plugins.json"
    if not installed.exists():
        print(f"{WARN}no plugin install found — see the README quickstart")
        return

    try:
        data = json.loads(installed.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(f"{WARN}could not read {installed}")
        return

    entries = [e for k, v in data.get("plugins", {}).items() if "mycelium" in k for e in v]
    if not entries:
        print(f"{WARN}mycelium plugin not installed — run: claude plugin install mycelium@mycelium")
        return

    sha = entries[0].get("gitCommitSha", "")
    if head and sha and sha != head:
        print(f"{WARN}skills pinned at {sha[:12]}, hooks run {head[:12]}")
        print("           run: claude plugin update mycelium@mycelium   (then restart)")
    elif head and sha == head:
        print(f"{OK}plugin at {sha[:12]} — same commit as the hooks")
    else:
        print(f"{OK}plugin installed ({sha[:12] or 'unknown commit'})")

    marketplaces = plugins / "known_marketplaces.json"
    if marketplaces.exists():
        try:
            mk = json.loads(marketplaces.read_text(encoding="utf-8")).get("mycelium", {})
        except (OSError, json.JSONDecodeError):
            return
        source = mk.get("source", {})
        path = source.get("path") or source.get("repo") or "?"
        if source.get("source") == "directory" and Path(path) == root:
            print(f"{OK}marketplace serves this checkout")
        else:
            print(f"{WARN}marketplace serves {path}, not {root}")
            print(f"           run: claude plugin marketplace add {root}")


def run(script: Path, *args: str) -> int:
    """Run a sibling installer, echoing its output."""
    r = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)
    out = (r.stdout + r.stderr).rstrip()
    if out:
        print("\n".join("  " + line.lstrip() for line in out.split("\n") if line.strip()))
    return r.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report and repair mycelium drift across Claude Code and Codex."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repo to check the AGENTS.md wiring of (default: current directory)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report only; don't reinstall anything. Exit 1 if anything needs action.",
    )
    args = parser.parse_args()

    root = mycelium_root()
    scripts = root / "skills" / "core" / "scripts"
    mode = ["--check"] if args.check else []

    head = report_install(root)
    report_claude(root, head)

    print("\nCodex skills")
    codex_rc = run(scripts / "install_codex_skills.py", *mode)

    repo = args.repo.resolve()
    print(f"\nRepo wiring — {repo}")
    repo_rc = run(scripts / "install_agents_md.py", "--target-dir", str(repo), *mode)

    if args.check and (codex_rc or repo_rc):
        print("\nRun without --check to fix the generated files.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
