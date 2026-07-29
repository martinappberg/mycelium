"""Tests for sync_agents.py — drift detection and malformed-state tolerance.

sync_agents is a diagnostic, so the property that matters most is that it never
crashes on a broken install: a half-written plugin manifest is exactly when you
reach for it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import sync_agents as sa  # noqa: E402

HEAD = "a" * 40
OTHER = "b" * 40


def _plugins_dir(tmp_path: Path, sha: str | None, marketplace_path: str | None) -> Path:
    """Build a fake ~/.claude/plugins with the given install/marketplace state."""
    p = tmp_path / "plugins"
    p.mkdir(parents=True, exist_ok=True)
    if sha is not None:
        (p / "installed_plugins.json").write_text(
            json.dumps(
                {"plugins": {"mycelium@mycelium": [{"gitCommitSha": sha, "scope": "user"}]}}
            ),
            encoding="utf-8",
        )
    if marketplace_path is not None:
        (p / "known_marketplaces.json").write_text(
            json.dumps(
                {"mycelium": {"source": {"source": "directory", "path": marketplace_path}}}
            ),
            encoding="utf-8",
        )
    return p


# --- git helper ------------------------------------------------------------


def test_git_returns_empty_outside_a_repo(tmp_path: Path) -> None:
    assert sa.git(tmp_path, "rev-parse", "HEAD") == ""


def test_git_reads_head_in_a_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    (tmp_path / "f").write_text("x")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "c"], check=True)
    assert len(sa.git(tmp_path, "rev-parse", "HEAD")) == 40


# --- install reporting -----------------------------------------------------


def test_report_install_survives_non_repo(tmp_path: Path, capsys) -> None:
    assert sa.report_install(tmp_path) == ""
    assert "cannot tell which version" in capsys.readouterr().out


# --- claude plugin drift ---------------------------------------------------


def test_flags_stale_plugin(tmp_path: Path, capsys) -> None:
    """The core failure mode: skills pinned behind the hooks."""
    sa.report_claude(tmp_path, HEAD, _plugins_dir(tmp_path, OTHER, str(tmp_path)))
    out = capsys.readouterr().out
    assert "skills pinned at" in out
    assert "claude plugin update" in out


def test_matching_sha_is_clean(tmp_path: Path, capsys) -> None:
    sa.report_claude(tmp_path, HEAD, _plugins_dir(tmp_path, HEAD, str(tmp_path)))
    out = capsys.readouterr().out
    assert "same commit as the hooks" in out
    assert "claude plugin update" not in out


def test_flags_marketplace_pointing_elsewhere(tmp_path: Path, capsys) -> None:
    sa.report_claude(tmp_path, HEAD, _plugins_dir(tmp_path, HEAD, "/somewhere/else"))
    out = capsys.readouterr().out
    assert "marketplace serves /somewhere/else" in out


def test_marketplace_serving_this_checkout_is_clean(tmp_path: Path, capsys) -> None:
    sa.report_claude(tmp_path, HEAD, _plugins_dir(tmp_path, HEAD, str(tmp_path)))
    assert "marketplace serves this checkout" in capsys.readouterr().out


def test_missing_plugin_install(tmp_path: Path, capsys) -> None:
    empty = tmp_path / "plugins"
    empty.mkdir()
    sa.report_claude(tmp_path, HEAD, empty)
    assert "no plugin install found" in capsys.readouterr().out


def test_plugin_installed_but_not_mycelium(tmp_path: Path, capsys) -> None:
    p = tmp_path / "plugins"
    p.mkdir()
    (p / "installed_plugins.json").write_text(json.dumps({"plugins": {"other@x": []}}))
    sa.report_claude(tmp_path, HEAD, p)
    assert "mycelium plugin not installed" in capsys.readouterr().out


def test_corrupt_manifest_does_not_crash(tmp_path: Path, capsys) -> None:
    p = tmp_path / "plugins"
    p.mkdir()
    (p / "installed_plugins.json").write_text("{ not json")
    sa.report_claude(tmp_path, HEAD, p)
    assert "could not read" in capsys.readouterr().out


def test_corrupt_marketplace_json_does_not_crash(tmp_path: Path, capsys) -> None:
    p = _plugins_dir(tmp_path, HEAD, None)
    (p / "known_marketplaces.json").write_text("{ not json")
    sa.report_claude(tmp_path, HEAD, p)  # must not raise
    assert "same commit as the hooks" in capsys.readouterr().out


def test_unknown_head_still_reports_plugin(tmp_path: Path, capsys) -> None:
    """A non-git install can't be compared, but the plugin is still reported."""
    sa.report_claude(tmp_path, "", _plugins_dir(tmp_path, OTHER, str(tmp_path)))
    out = capsys.readouterr().out
    assert "plugin installed" in out
    assert "claude plugin update" not in out


# --- end to end ------------------------------------------------------------


def test_check_exits_nonzero_on_drift(tmp_path: Path) -> None:
    """--check against a repo with no wiring must fail, not pass silently."""
    r = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parent / "sync_agents.py"),
            "--check",
            "--repo",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "CODEX_HOME": str(tmp_path)},
    )
    assert r.returncode == 1
    assert "Run without --check" in r.stdout
