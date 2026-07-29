"""Tests for install_codex_skills.py — frontmatter, path rewriting, drift."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import install_codex_skills as ics  # noqa: E402


def _fake_mycelium(tmp_path: Path, commands: dict[str, str]) -> Path:
    """Build a minimal mycelium tree with the given commands/*.md files."""
    root = tmp_path / "mycelium"
    (root / "commands").mkdir(parents=True)
    for name, body in commands.items():
        (root / "commands" / name).write_text(body, encoding="utf-8")
    return root


FOLDED = """---
description: >
  ALWAYS use this skill when the user mentions "mycelium".
  Handles project initialization.
---

# Mycelium Core

Run `skills/core/scripts/init_repo.py` to scaffold.
See /mycelium:review for reviews and /mycelium:nonexistent for nothing.
"""

INLINE = """---
description: Review code changes.
---

# Review
"""


# --- frontmatter parsing ---------------------------------------------------


def test_split_frontmatter_extracts_block() -> None:
    fm, body = ics.split_frontmatter(INLINE)
    assert "description: Review code changes." in fm
    assert body.lstrip().startswith("# Review")


def test_split_frontmatter_without_frontmatter() -> None:
    fm, body = ics.split_frontmatter("# Just a title\n")
    assert fm == ""
    assert body == "# Just a title\n"


def test_split_frontmatter_unterminated_is_not_frontmatter() -> None:
    text = "---\ndescription: dangling\n\n# Body\n"
    fm, body = ics.split_frontmatter(text)
    assert fm == ""
    assert body == text


def test_parse_description_folded_joins_with_spaces() -> None:
    fm, _ = ics.split_frontmatter(FOLDED)
    desc = ics.parse_description(fm)
    assert desc == (
        'ALWAYS use this skill when the user mentions "mycelium". '
        "Handles project initialization."
    )


def test_parse_description_inline() -> None:
    fm, _ = ics.split_frontmatter(INLINE)
    assert ics.parse_description(fm) == "Review code changes."


def test_parse_description_stops_at_sibling_key() -> None:
    fm = "description: >\n  first line\nother: value\n"
    assert ics.parse_description(fm) == "first line"


def test_parse_description_missing() -> None:
    assert ics.parse_description("name: thing\n") == ""


# --- path rewriting --------------------------------------------------------


def test_rewrite_paths_absolutises_relative_refs() -> None:
    out = ics.rewrite_paths("Run `skills/core/scripts/x.py` now", Path("/opt/myc"))
    assert "/opt/myc/skills/core/scripts/x.py" in out


def test_rewrite_paths_leaves_absolute_paths_alone() -> None:
    text = "Run `/opt/myc/skills/core/scripts/x.py` now"
    assert ics.rewrite_paths(text, Path("/opt/myc")) == text


def test_rewrite_paths_is_idempotent() -> None:
    once = ics.rewrite_paths("see skills/core/references/a.md", Path("/opt/myc"))
    assert ics.rewrite_paths(once, Path("/opt/myc")) == once


def test_rewrite_command_refs_only_rewrites_known() -> None:
    out = ics.rewrite_command_refs(
        "use /mycelium:review not /mycelium:ghost",
        {"mycelium-review"},
    )
    assert "mycelium-review" in out
    assert "/mycelium:ghost" in out


# --- generation ------------------------------------------------------------


def test_build_skill_emits_name_and_description(tmp_path: Path) -> None:
    root = _fake_mycelium(tmp_path, {"core.md": FOLDED})
    out = ics.build_skill(root / "commands" / "core.md", root, {"mycelium-core"})
    assert out.startswith("---\nname: mycelium-core\ndescription: \"")
    assert '\\"mycelium\\"' in out  # inner quotes escaped for YAML


def test_build_skill_injects_codex_preamble(tmp_path: Path) -> None:
    root = _fake_mycelium(tmp_path, {"core.md": FOLDED})
    out = ics.build_skill(root / "commands" / "core.md", root, {"mycelium-core"})
    assert "## Running under Codex" in out
    assert "No hooks fire" in out
    assert "Never hand-edit a table registry" in out


def test_build_skill_rewrites_body_paths(tmp_path: Path) -> None:
    root = _fake_mycelium(tmp_path, {"core.md": FOLDED})
    out = ics.build_skill(root / "commands" / "core.md", root, {"mycelium-core"})
    assert f"{root}/skills/core/scripts/init_repo.py" in out


def test_build_skill_requires_description(tmp_path: Path) -> None:
    root = _fake_mycelium(tmp_path, {"bare.md": "# No frontmatter\n"})
    try:
        ics.build_skill(root / "commands" / "bare.md", root, set())
    except ValueError as e:
        assert "no description" in str(e)
    else:
        raise AssertionError("expected ValueError for missing description")


# --- install / check / uninstall -------------------------------------------


def test_install_creates_skill_dirs(tmp_path: Path) -> None:
    root = _fake_mycelium(tmp_path, {"core.md": FOLDED, "review.md": INLINE})
    dest = tmp_path / "codex" / "skills"
    ics.install(root, dest, None)
    assert (dest / "mycelium-core" / "SKILL.md").exists()
    assert (dest / "mycelium-review" / "SKILL.md").exists()


def test_install_is_idempotent(tmp_path: Path) -> None:
    root = _fake_mycelium(tmp_path, {"core.md": FOLDED})
    dest = tmp_path / "codex" / "skills"
    ics.install(root, dest, None)
    first = (dest / "mycelium-core" / "SKILL.md").read_text()
    ics.install(root, dest, None)
    assert (dest / "mycelium-core" / "SKILL.md").read_text() == first


def test_check_reports_current(tmp_path: Path) -> None:
    root = _fake_mycelium(tmp_path, {"core.md": FOLDED})
    dest = tmp_path / "codex" / "skills"
    ics.install(root, dest, None)
    assert ics.check(root, dest, None) == 0


def test_check_detects_missing(tmp_path: Path) -> None:
    root = _fake_mycelium(tmp_path, {"core.md": FOLDED})
    assert ics.check(root, tmp_path / "codex" / "skills", None) == 1


def test_check_detects_stale(tmp_path: Path) -> None:
    root = _fake_mycelium(tmp_path, {"core.md": FOLDED})
    dest = tmp_path / "codex" / "skills"
    ics.install(root, dest, None)
    (root / "commands" / "core.md").write_text(
        FOLDED + "\nA newly documented step.\n", encoding="utf-8"
    )
    assert ics.check(root, dest, None) == 1


def test_only_filters_commands(tmp_path: Path) -> None:
    root = _fake_mycelium(tmp_path, {"core.md": FOLDED, "review.md": INLINE})
    dest = tmp_path / "codex" / "skills"
    ics.install(root, dest, ["review"])
    assert (dest / "mycelium-review").exists()
    assert not (dest / "mycelium-core").exists()


def test_only_accepts_prefixed_name(tmp_path: Path) -> None:
    root = _fake_mycelium(tmp_path, {"core.md": FOLDED, "review.md": INLINE})
    dest = tmp_path / "codex" / "skills"
    ics.install(root, dest, ["mycelium-review"])
    assert (dest / "mycelium-review").exists()
    assert not (dest / "mycelium-core").exists()


def test_only_rejects_unknown(tmp_path: Path) -> None:
    root = _fake_mycelium(tmp_path, {"core.md": FOLDED})
    try:
        ics.discover(root, ["ghost"])
    except ValueError as e:
        assert "ghost" in str(e)
    else:
        raise AssertionError("expected ValueError for unknown command")


def test_uninstall_leaves_foreign_skills(tmp_path: Path) -> None:
    root = _fake_mycelium(tmp_path, {"core.md": FOLDED})
    dest = tmp_path / "codex" / "skills"
    ics.install(root, dest, None)
    (dest / "imagegen").mkdir()
    (dest / "imagegen" / "SKILL.md").write_text("not ours", encoding="utf-8")
    ics.uninstall(dest)
    assert not (dest / "mycelium-core").exists()
    assert (dest / "imagegen" / "SKILL.md").read_text() == "not ours"


def test_codex_home_honours_env(monkeypatch) -> None:
    monkeypatch.setenv("CODEX_HOME", "/tmp/custom-codex")
    assert ics.codex_home() == Path("/tmp/custom-codex")


def test_codex_home_defaults(monkeypatch) -> None:
    monkeypatch.delenv("CODEX_HOME", raising=False)
    assert ics.codex_home() == Path.home() / ".codex"


# --- the real command set --------------------------------------------------


def test_real_commands_all_convert() -> None:
    """Every shipped command must produce a valid Codex skill."""
    root = ics.mycelium_root()
    sources = ics.discover(root, None)
    known = {ics.SKILL_PREFIX + s.stem for s in sources}
    assert len(sources) >= 6
    for source in sources:
        out = ics.build_skill(source, root, known)
        assert out.startswith("---\nname: mycelium-")
        # No bare relative mycelium path may survive into a Codex skill.
        assert "`skills/core/" not in out
