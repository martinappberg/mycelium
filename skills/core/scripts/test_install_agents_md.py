"""Tests for install_agents_md.py — splice idempotency, pointer, drift."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import install_agents_md as iam  # noqa: E402

ROOT = iam.mycelium_root()


# --- splice ----------------------------------------------------------------


def test_splice_appends_when_absent() -> None:
    out = iam.splice("# Repo\n\nSome rules.\n", "BLOCK")
    assert out.startswith("# Repo")
    assert out.rstrip().endswith("BLOCK")


def test_splice_replaces_existing_block() -> None:
    existing = f"# Repo\n\n{iam.BEGIN}\nold\n{iam.END}\n\nTail text.\n"
    out = iam.splice(existing, f"{iam.BEGIN}\nnew\n{iam.END}")
    assert "old" not in out
    assert "new" in out
    assert "Tail text." in out


def test_splice_is_idempotent() -> None:
    block = f"{iam.BEGIN}\nbody\n{iam.END}"
    once = iam.splice("# Repo\n", block)
    assert iam.splice(once, block) == once


def test_splice_preserves_content_after_block() -> None:
    existing = f"{iam.BEGIN}\nold\n{iam.END}\n\n## Section 12\n\nKeep me.\n"
    out = iam.splice(existing, f"{iam.BEGIN}\nnew\n{iam.END}")
    assert "## Section 12" in out
    assert "Keep me." in out


def test_splice_with_missing_end_marker_appends() -> None:
    """A hand-deleted END must not swallow the rest of the file."""
    existing = f"# Repo\n\n{iam.BEGIN}\nhalf a block\n\n## Later section\n"
    out = iam.splice(existing, f"{iam.BEGIN}\nnew\n{iam.END}")
    assert "## Later section" in out
    assert "new" in out


def test_splice_into_empty_file() -> None:
    assert iam.splice("", "BLOCK") == "BLOCK\n"


# --- unmanaged-section detection -------------------------------------------


def test_detects_unmanaged_living_section() -> None:
    assert iam.has_unmanaged_living_section("We track `.living/decisions.md` here.")


def test_managed_block_is_not_flagged_as_unmanaged() -> None:
    text = f"# Repo\n\n{iam.BEGIN}\nmentions .living/ inside\n{iam.END}\n"
    assert not iam.has_unmanaged_living_section(text)


# --- install ---------------------------------------------------------------


def test_install_creates_agents_md(tmp_path: Path) -> None:
    iam.install(tmp_path, ROOT)
    text = (tmp_path / "AGENTS.md").read_text()
    assert iam.BEGIN in text and iam.END in text
    assert "post-action protocol" in text


def test_install_writes_root_pointer(tmp_path: Path) -> None:
    iam.install(tmp_path, ROOT)
    assert (tmp_path / iam.ROOT_POINTER).read_text().strip() == str(ROOT)


def test_install_gitignores_pointer(tmp_path: Path) -> None:
    iam.install(tmp_path, ROOT)
    assert iam.ROOT_POINTER in (tmp_path / ".gitignore").read_text()


def test_install_gitignore_is_idempotent(tmp_path: Path) -> None:
    iam.install(tmp_path, ROOT)
    first = (tmp_path / ".gitignore").read_text()
    iam.install(tmp_path, ROOT)
    assert (tmp_path / ".gitignore").read_text() == first


def test_install_preserves_existing_agents_content(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# House rules\n\nAlways cite sources.\n")
    iam.install(tmp_path, ROOT)
    text = (tmp_path / "AGENTS.md").read_text()
    assert "Always cite sources." in text
    assert iam.BEGIN in text


def test_install_twice_leaves_one_block(tmp_path: Path) -> None:
    iam.install(tmp_path, ROOT)
    iam.install(tmp_path, ROOT)
    assert (tmp_path / "AGENTS.md").read_text().count(iam.BEGIN) == 1


def test_agents_md_has_no_absolute_paths(tmp_path: Path) -> None:
    """AGENTS.md is committed and shared — it must stay machine-independent."""
    iam.install(tmp_path, ROOT)
    assert str(ROOT) not in (tmp_path / "AGENTS.md").read_text()


# --- check -----------------------------------------------------------------


def test_check_fails_on_fresh_repo(tmp_path: Path) -> None:
    assert iam.check(tmp_path, ROOT) == 1


def test_check_passes_after_install(tmp_path: Path) -> None:
    iam.install(tmp_path, ROOT)
    assert iam.check(tmp_path, ROOT) == 0


def test_check_detects_stale_block(tmp_path: Path) -> None:
    iam.install(tmp_path, ROOT)
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        agents.read_text().replace("post-action protocol", "outdated wording")
    )
    assert iam.check(tmp_path, ROOT) == 1


def test_check_detects_moved_install(tmp_path: Path) -> None:
    iam.install(tmp_path, ROOT)
    (tmp_path / iam.ROOT_POINTER).write_text("/somewhere/else\n")
    assert iam.check(tmp_path, ROOT) == 1
