---
name: ops-setup
description: One-time setup of oss-steward in a target repository — scaffolds the .ops/ state directory, default policy.yaml, the proposals digest issue, and the scheduled GitHub Actions workflow. Use when the user says "set up oss-steward", "initialize ops", "install steward in this repo", or wants agent-managed issue triage for a repository.
---

# ops-setup

One-time initialization of oss-steward for the current repository. Run this from
the root of the target repo's working copy.

## Prerequisites

1. `gh auth status` succeeds and the user has write access to the repo.
2. Identify the repo: `gh repo view --json nameWithOwner -q .nameWithOwner`.
   Call this `<owner/repo>` below.

## Steps

1. **Scaffold `.ops/`** (skip any file that already exists — never overwrite):
   ```bash
   mkdir -p .ops/proposals .ops/audit .ops/reports
   cp "${CLAUDE_PLUGIN_ROOT}/templates/policy.yaml" .ops/policy.yaml
   echo '{}' > .ops/cursor.json
   touch .ops/processed.jsonl
   ```

2. **Tune the policy with the maintainer.** Open `.ops/policy.yaml` and adjust
   `allowed-labels` to the labels this repo actually uses
   (`gh label list` shows them). Explain the three risk tiers and that
   promoting an action to `low` is always a manual edit of this file.

3. **Install Claude Code settings** (permissions allow-list + model config):
   ```bash
   mkdir -p .claude
   cp -n "${CLAUDE_PLUGIN_ROOT}/templates/settings.json" .claude/settings.json
   ```
   This auto-approves the Bash/Read/Write the skills need so the scheduled run is
   unattended. To point at a non-Anthropic endpoint (e.g. MiniMax), edit the
   `env` block — see `${CLAUDE_PLUGIN_ROOT}/docs/MODELS.md`. Never put the API
   key here; it is a repo secret (next step).

4. **Install a runner.** Ask the maintainer how they want batches to run, then
   install the matching runner (you can install both):

   - **Local machine** (no GitHub Actions; uses their `gh`/`claude` login):
     ```bash
     cp "${CLAUDE_PLUGIN_ROOT}/templates/run-local.sh" .ops/run-local.sh
     chmod +x .ops/run-local.sh
     ```
     Point them at `docs/LOCAL.md` for one-shot, `--interval`, cron, and launchd
     usage. Nothing else is needed — `/oss-steward:ops-run` already works
     interactively too.

   - **GitHub Actions** (scheduled in CI):
     ```bash
     mkdir -p .github/workflows
     cp "${CLAUDE_PLUGIN_ROOT}/templates/ops-run.yml" .github/workflows/ops-run.yml
     ```
     Remind the maintainer to add the credential repo secret
     (Settings → Secrets and variables → Actions): `ANTHROPIC_API_KEY` for the
     official Anthropic API, or `ANTHROPIC_AUTH_TOKEN` for a third-party gateway
     (see docs/MODELS.md). Without it the scheduled run cannot start.

5. **Create the digest issue** (the human-approval surface):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ops_sync.py" --ops .ops --repo <owner/repo>
   ```
   This creates the "🤖 Ops Proposals" issue and records its number in
   `.ops/digest.json`.

6. **Commit everything** (`.ops/` includes `run-local.sh`; add the workflow only
   if you installed it):
   ```bash
   git add .ops/ .claude/settings.json
   [ -f .github/workflows/ops-run.yml ] && git add .github/workflows/ops-run.yml
   git commit -m "chore: set up oss-steward"
   ```

7. **Verify:** run one dry-run batch and show the user the result:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ops_fetch.py" --ops .ops --repo <owner/repo> --limit 5
   ```

## Rules

- Never overwrite an existing `.ops/policy.yaml` — the maintainer owns it.
- Do not edit risk tiers yourself; only the maintainer changes them.
