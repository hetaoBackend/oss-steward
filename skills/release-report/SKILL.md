---
name: release-report
description: Generate changelog drafts, weekly reports, and repo health summaries from merged PRs and closed issues — read-only plus local report files; publishing releases stays human-only. Use when the user says "draft the changelog", "weekly report", "release notes", or on a low-frequency schedule.
---

# release-report

Pure read + generate. This skill performs **no GitHub writes at all** — its
output is Markdown files under `.ops/reports/`, committed with the ops state.
Publishing a release (`gh release create`) is permanently human-only.

## Flow

1. Identify the repo (call it `<owner/repo>`) and the window: since the last
   report in `.ops/reports/` (or the last release tag,
   `gh release list --limit 1`), defaulting to the last 7 days.

2. Collect read-only data:
   ```bash
   gh pr list --state merged --search "merged:>=<window-start>" --json number,title,author,labels
   gh issue list --state closed --search "closed:>=<window-start>" --json number,title,labels
   gh issue list --state open --json number --jq length
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ops_stats.py" --ops .ops
   ```

3. **Changelog draft** → `.ops/reports/<YYYY-MM-DD>-changelog.md`:
   group merged PRs by type (features / fixes / docs / chores, inferred from
   labels and titles), one line each with PR number and author credit. Mark
   anything that looks breaking. This is a *draft* for the maintainer to edit
   into real release notes.

4. **Weekly report** → `.ops/reports/<YYYY-MM-DD>-weekly.md`:
   - activity: issues opened/closed, PRs merged, new contributors;
   - steward health: the `ops_stats.py` output — proposals by outcome,
     acceptance rates per action type;
   - **promotion suggestions** from ops_stats, verbatim, addressed to the
     maintainer (they decide; you never edit policy.yaml risk tiers);
   - notable threads needing human attention (failed/stale proposals from the
     digest).

5. Commit the reports with the ops state:
   ```bash
   git add .ops/reports/
   git commit -m "ops: reports $(date -u +%Y-%m-%d)"
   ```

6. Tell the user where the files are and the three most important takeaways.

## Rules

- No GitHub writes. If asked to publish a release, decline and point the
  maintainer at the changelog draft.
- Credit every external contributor by login in the changelog.
