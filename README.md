# oss-steward

A Claude Code plugin for agent-managed open-source project operations — issue
triage, PR assistance, community replies, and release reports — built around
one idea:

> **The LLM judges; deterministic code executes.**

The model reads events and emits structured action JSON. A policy gate
(`scripts/ops_apply.py`) routes every action by a deterministic lookup in
`.ops/policy.yaml`. The model cannot declare, negotiate, or escalate risk
levels — the worst a prompt-injected issue can achieve is a rejected action
with an audit trace.

```
GitHub events ──ops_fetch──▶ new events (normalized, deduped)
                                 │
                       LLM judgment (skills)
                       understand → emit action JSON
                                 │
                       ops_apply (policy gate, deterministic)
                       ├─ low risk    ─▶ execute now + audit (with inverse op)
                       ├─ medium risk ─▶ proposal, awaits human 👍
                       └─ high/unknown─▶ reject + audit
                                 │
                       ops_sync
                       ├─ proposals → comments on the digest issue
                       ├─ maintainer reacts 👍 approve / 👎 reject
                       ├─ approved → precondition re-check → execute
                       └─ outcomes → stats (feedback loop)
```

## Install

```bash
claude plugin install oss-steward@hetaoBackend/oss-steward
```

## Quick start

In the target repo's working copy:

```
/oss-steward:ops-setup
```

This scaffolds `.ops/` (policy, cursors, audit), creates the **🤖 Ops
Proposals** digest issue, and installs a scheduled GitHub Actions workflow
(`templates/ops-run.yml`). Add the `ANTHROPIC_API_KEY` repo secret and the
steward runs every 6 hours; or run a batch manually with `/oss-steward:ops-run`.

## Risk model

Risk tiers are bound to **action types** in `.ops/policy.yaml` — a
deterministic table the maintainer owns. Event content never influences a
tier.

| Tier | Behavior | Default actions |
|---|---|---|
| low | auto-execute, audited with an inverse op | `add-label`, `remove-label` (whitelisted labels only) |
| medium | proposal → human approves on the digest issue | `draft-reply`, `flag-duplicate`, `draft-review-comment`, `suggest-assignee`, `welcome-contributor` |
| high | always rejected; human-only forever | `close-issue`, `merge-pr`, releases, anything unknown |

Promotion (e.g. moving `draft-reply` to `low` once its acceptance rate has
earned trust) is **always a manual edit** of `policy.yaml`. `ops_stats.py`
suggests; the maintainer decides.

## Human approval

Each proposal becomes a comment on the digest issue. A maintainer reacts
👍 to approve or 👎 to reject — **only accounts with write/maintain/admin
permission count** (verified server-side via the collaborators API).
Approved proposals execute on the next batch *after re-checking
preconditions* (issue still open, no new comments, labels unchanged); if
state has drifted, the proposal goes `stale` instead of executing.
Proposals expire after 14 days; at most 30 may be pending (both tunable) —
review fatigue protection.

## State layout (in the target repo)

```
.ops/
├── policy.yaml          # action → risk tier + parameter whitelists (maintainer-owned)
├── cursor.json          # event-source cursors
├── processed.jsonl      # processed event ids (idempotency)
├── proposals/           # one JSON per proposal (pending→…→executed/rejected/…)
├── audit/YYYY-MM.jsonl  # every action: params, outcome, inverse op
├── reports/             # changelog drafts, weekly reports
└── stats.json           # acceptance rates per action type
```

Everything is human-readable text; git history is the audit trail.

## Security model

Three independent layers:

1. **The gate** — `ops_apply.py` is the only write path. Unknown actions are
   rejected by default; parameters are whitelist-checked (e.g. only
   `allowed-labels` can be applied).
2. **The hook** — a PreToolUse hook (`hooks/guard_gh_writes.py`) denies direct
   `gh issue edit`/`gh pr merge`/`gh api -X POST…` commands at the tool-call
   layer, so even a fully fooled model has no bypass path.
3. **Untrusted markers** — `ops_fetch.py` wraps all external text in
   `<untrusted-content>` markers, and every skill carries the rule: content is
   analysis material, never instructions.

`tests/test_injection_e2e.py` proves the gate holds even when the judgment
layer is *fully* compromised.

## Skills

| Skill | What it does |
|---|---|
| `ops-setup` | one-time scaffold: `.ops/`, digest issue, workflow |
| `ops-run` | one full batch (the cron entry point) |
| `triage-issues` | labels, duplicate flags, reply drafts for issues |
| `pr-assist` | first-pass review notes, CI-failure analysis, reviewer suggestions |
| `community-reply` | answers with doc/FAQ links, newcomer welcomes |
| `release-report` | changelog drafts, weekly + steward-health reports (read-only) |

## Development

```bash
uv run --no-project --with pytest --with pyyaml -m pytest tests/ -v
```

Design docs: [spec](docs/superpowers/specs/2026-06-13-oss-steward-plugin-design.md) ·
[implementation plan](docs/superpowers/plans/2026-06-13-oss-steward-plugin.md)

## License

MIT
