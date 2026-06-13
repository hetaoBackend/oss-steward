# Running oss-steward locally (no GitHub Actions)

Everything the steward does works from your own machine: `gh` uses your local
login, `claude` uses your local model config, and the gh-write guard hook stays
active. There are three ways to run it.

## Prerequisites (once)

```bash
gh auth login
claude plugin marketplace add hetaoBackend/oss-steward
claude plugin install oss-steward@oss-steward
cd /path/to/your/repo
# in Claude Code:
/oss-steward:ops-setup
```

`ops-setup` writes `.ops/`, `.claude/settings.json` (model + permissions), the
digest issue, and drops `.ops/run-local.sh` for headless runs below.

## 1. Interactive

In Claude Code, in the repo:

```
/oss-steward:ops-run
```

You approve the Bash steps as they run (or rely on the `.claude/settings.json`
allow-list to auto-approve). Best for trying it out and watching what it does.

## 2. One-shot headless

```bash
.ops/run-local.sh                 # one batch
.ops/run-local.sh --dry-run       # rehearse, no GitHub writes
.ops/run-local.sh --commit --push # persist .ops/ audit state to git
```

See `.ops/run-local.sh --help` for all flags. A `.ops/lock` directory prevents
overlap with a scheduled run.

## 3. Scheduled on your machine

### Foreground loop (simplest; keep a terminal open)

```bash
.ops/run-local.sh --interval 6h --commit
```

### cron

cron runs with a **minimal environment** — `claude`, `gh`, and `node` are
usually not on its `PATH`, and your shell's `ANTHROPIC_*` exports are not loaded.
Use a wrapper that sets up the environment:

```bash
# ~/oss-steward-cron.sh
#!/usr/bin/env bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"   # where claude/gh/node live
export ANTHROPIC_AUTH_TOKEN="…"        # or rely on ~/.claude/settings.json (see docs/MODELS.md)
cd /path/to/your/repo
exec .ops/run-local.sh --commit --push >> "$HOME/.oss-steward.log" 2>&1
```

```bash
chmod +x ~/oss-steward-cron.sh
crontab -e
# run every 6 hours:
0 */6 * * * /Users/you/oss-steward-cron.sh
```

Tip: put model/endpoint config and the credential in `~/.claude/settings.json`
so the wrapper doesn't need to export secrets. `which claude gh node` tells you
the `PATH` to set.

### launchd (macOS, survives logout)

`~/Library/LaunchAgents/com.oss-steward.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.oss-steward</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/you/oss-steward-cron.sh</string>
  </array>
  <key>StartInterval</key><integer>21600</integer>   <!-- 6h -->
  <key>StandardOutPath</key><string>/Users/you/.oss-steward.log</string>
  <key>StandardErrorPath</key><string>/Users/you/.oss-steward.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.oss-steward.plist
```

## Notes

- **State persistence:** `.ops/` on disk is the source of truth between runs
  (idempotency, proposals, audit). `--commit`/`--push` is for sharing the audit
  trail and surviving a clean checkout; the steward works without it.
- **Approval still happens on GitHub:** local runs publish proposals to the
  digest issue exactly like CI; you approve with 👍 from any device.
- **No host secrets in the repo:** the credential lives in your env or
  `~/.claude/settings.json`, never in the committed `.claude/settings.json`.
