## Mycelium — the `.living/` working layer

This repo is mycelium-enabled. `.living/` is separate from the repo's content: the
repo holds the work, `.living/` holds the record of how the work is being done.

| File | Holds |
|---|---|
| `.living/decisions.md` | Choices we made, with alternatives and rationale |
| `.living/learnings.md` | Things that surprised us — gotchas, failures, edge cases |
| `.living/conventions.md` | Conventions crystallized from repeated learnings |
| `.living/log/LOG_REGISTRY.md` | Session-by-session record |
| `.living/findings/FINDINGS_REGISTRY.md` | Registered findings, one row per F-NNN |

### The post-action protocol

After any substantial piece of work: log non-obvious choices to `decisions.md`,
surprises to `learnings.md`, and write a session summary.

**Who enforces this depends on which agent you are.** Under Claude Code,
mycelium's hooks fire on SessionStart, PostToolUse, and Stop — they open the
session log, track edits, and can block session end if substantial work happened
without `.living/` being updated. **Under Codex, or any agent without those
hooks, nothing fires and the protocol is yours to enforce.** Follow it because
nothing else will.

### Concurrency — more than one agent may be working here

`.living/` is shared across every agent in this working tree, and a Claude chat
and a Codex session can be live at the same time. Any read-modify-write of a
shared file must be serialised through mycelium's helpers, which take an
advisory `flock` and write atomically.

The mycelium install path for this machine is in `.living/mycelium-root` (local,
gitignored — each machine writes its own). Resolve the helpers through it:

```bash
MYC="$(cat .living/mycelium-root)"

# Claim a YYYY-MM-DD-NNN session-log slot atomically
python3 "$MYC/skills/core/scripts/allocate_session_slot.py"

# Upsert a row in a markdown TABLE registry (LOG / FINDINGS / TODO)
python3 "$MYC/skills/core/scripts/upsert_manifest_row.py" <file> <key> "<row>"
```

**Never hand-edit a table registry with an editor tool.** An agent holding the
flock will not see your write, and one of the two rows is silently lost. This is
the one place where using the obvious tool is the wrong move.

Safe without a lock: appending to `.living/learnings.md`, `.living/decisions.md`,
and `.living/conventions.md`. These are append-only and POSIX `O_APPEND` never
overwrites — at worst, entries interleave. The YAML-block ANALYSIS/DATA manifests
are edited normally; they aren't tables.

Full contract: `skills/core/references/concurrency.md` and
`skills/core/references/codex-parity.md` in the mycelium install.

### Skills

The same mycelium skills are available in both tools, under each tool's naming:

| Claude Code | Codex | Does |
|---|---|---|
| `/mycelium:core` | `mycelium-core` | Living-repo orchestrator: init, crystallize, todo ideas, transfer |
| `/mycelium:analyze` | `mycelium-analyze` | Start or continue an analysis |
| `/mycelium:report` | `mycelium-report` | Generate a structured report |
| `/mycelium:ideas` | `mycelium-ideas` | Brainstorm with disciplinary personas |
| `/mycelium:ingest` | `mycelium-ingest` | Import data with metadata and provenance |
| `/mycelium:review` | `mycelium-review` | Analysis-aware review of a PR, commit, or diff |
| `/mycelium:codex-review` | `mycelium-codex-review` | Address Codex review comments and audit the branch |
| `/mycelium:transfer` | `mycelium-transfer` | Cross-pollinate learnings across sibling projects |

Re-sync the Codex copies after a mycelium update:

```bash
python3 "$(cat .living/mycelium-root)/skills/core/scripts/install_codex_skills.py" --check
```
