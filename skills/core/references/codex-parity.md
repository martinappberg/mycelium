# Codex parity: running mycelium under both agents

Mycelium was built as a Claude Code plugin. Codex can run the same workflows on
the same `.living/` knowledge base, but the two agents do not have the same
machinery, and the gap is not cosmetic — it is the difference between a
protocol that is *enforced* and one that is *followed*.

## What each agent has

| | Claude Code | Codex |
|---|---|---|
| Skills | plugin commands, `/mycelium:core` | generated `$CODEX_HOME/skills/mycelium-core/SKILL.md` |
| Path resolution | plugin root | absolute paths baked in at install |
| Post-action enforcement | **hooks** — fire regardless of the model | **the model** — stated in AGENTS.md |
| Session log lifecycle | opened by `mycelium-health.sh` at SessionStart, closed by `mycelium-stop-check.sh` | opened and closed by the agent |
| Session isolation | `session_id`-scoped run dirs (`concurrency.md`) | no session id; nothing to isolate |
| `.living/` locking | helper scripts | the same helper scripts |

Two lines matter.

**Enforcement.** Claude's hooks run whether or not the model cooperates —
`mycelium-stop-check.sh` can block session end when substantial work happened
without `.living/` being updated. Codex has no hook system at all. So under
Codex the post-action protocol is an instruction, and instructions can be
skipped. This is a real asymmetry and the bridge does not pretend otherwise; it
states the protocol prominently in both the skill preamble and AGENTS.md, and
that is the strongest available guarantee.

**Locking.** This one *is* at parity, and it is the one that has to be. The
lock helpers are plain Python using `fcntl.flock`, so they serialise correctly
across processes no matter which agent started them. A Codex session and a
Claude chat writing `LOG_REGISTRY.md` through `upsert_manifest_row.py` are safe
against each other. A Codex session hand-editing it with an editor tool is not —
it will silently drop whichever row the other agent wrote. That is why the
"never hand-edit a table registry" rule appears in the Codex preamble in
stronger terms than Claude needs.

## Session identity across agents

`mycelium-run-paths.sh` scopes transient sentinels by Claude's `session_id`.
Codex never runs hooks, so it never touches those sentinels and cannot collide
with them — the scoping is a Claude-internal concern.

What both agents *do* share is the session-log slot namespace,
`.living/log/YYYY-MM-DD-NNN-*.md`. `allocate_session_slot.py` claims a slot with
`O_EXCL`, which is atomic against any process on the machine. A Codex session
and a Claude chat starting at the same moment get different slots.

## Installing

```bash
# Generate the Codex skills from commands/*.md
python3 skills/core/scripts/install_codex_skills.py

# Install the protocol into a repo's AGENTS.md + write .living/mycelium-root
python3 skills/core/scripts/install_agents_md.py --target-dir /path/to/repo
```

`init_repo.py` runs both as part of a normal init. Pass `--no-codex` to skip.

## Keeping them in sync

The Codex skills are **generated**, not symlinked — the frontmatter needs a
`name:` field Claude commands don't carry, and the relative paths in command
bodies have to be absolutised because Codex has no plugin root to resolve them
against. Generated copies go stale when mycelium updates, so both installers
have a `--check` mode that regenerates in memory and diffs:

```bash
python3 skills/core/scripts/install_codex_skills.py --check   # exit 1 if stale
python3 skills/core/scripts/install_agents_md.py --check
```

Re-run without `--check` to bring them current. Worth doing after any
`/plugin update mycelium`, and after moving the mycelium install (the absolute
paths baked into the Codex skills and `.living/mycelium-root` both point at
wherever it was when you last installed).
