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

3. **Install the scheduled workflow:**
   ```bash
   mkdir -p .github/workflows
   cp "${CLAUDE_PLUGIN_ROOT}/templates/ops-run.yml" .github/workflows/ops-run.yml
   ```
   Remind the maintainer to add the `ANTHROPIC_API_KEY` repo secret
   (Settings → Secrets and variables → Actions). Without it the scheduled run
   cannot start.

4. **Create the digest issue** (the human-approval surface):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ops_sync.py" --ops .ops --repo <owner/repo>
   ```
   This creates the "🤖 Ops Proposals" issue and records its number in
   `.ops/digest.json`.

5. **Commit everything:**
   ```bash
   git add .ops/ .github/workflows/ops-run.yml
   git commit -m "chore: set up oss-steward"
   ```

6. **Verify:** run one dry-run batch and show the user the result:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ops_fetch.py" --ops .ops --repo <owner/repo> --limit 5
   ```

## Rules

- Never overwrite an existing `.ops/policy.yaml` — the maintainer owns it.
- Do not edit risk tiers yourself; only the maintainer changes them.
