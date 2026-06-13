#!/usr/bin/env bash
# Run oss-steward locally — no GitHub Actions required.
#
# Prereqs: `gh auth login` done, the oss-steward plugin installed, and
# `/oss-steward:ops-setup` already run in this repo (so .ops/ exists).
# Model + credentials come from your normal Claude Code config (shell env or
# ~/.claude/settings.json) merged with this repo's .claude/settings.json — see
# docs/MODELS.md.
#
# Usage:
#   .ops/run-local.sh                    # one batch in the current repo
#   .ops/run-local.sh --repo owner/name  # target an explicit repo
#   .ops/run-local.sh --dry-run          # rehearse: no writes to GitHub
#   .ops/run-local.sh --interval 6h      # loop every 6h (Ctrl-C to stop)
#   .ops/run-local.sh --commit           # commit .ops/ state locally after the run
#   .ops/run-local.sh --commit --push    # and push it
#   .ops/run-local.sh --yolo             # add --dangerously-skip-permissions
#
# A directory lock (.ops/lock) keeps two runs (e.g. cron + manual) from
# overlapping. The gh-write guard hook stays active regardless of flags.
set -euo pipefail

REPO=""
DRY=""
INTERVAL=""
DO_COMMIT=0
DO_PUSH=0
CLAUDE_FLAGS="${CLAUDE_FLAGS:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2;;
    --dry-run) DRY=1; shift;;
    --interval) INTERVAL="$2"; shift 2;;
    --commit) DO_COMMIT=1; shift;;
    --push) DO_COMMIT=1; DO_PUSH=1; shift;;
    --yolo) CLAUDE_FLAGS="$CLAUDE_FLAGS --dangerously-skip-permissions"; shift;;
    -h|--help) sed -n '2,28p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

command -v claude >/dev/null || { echo "claude CLI not found" >&2; exit 1; }
command -v gh >/dev/null || { echo "gh CLI not found (run: gh auth login)" >&2; exit 1; }
[ -d .ops ] || { echo "no .ops/ here — run /oss-steward:ops-setup first" >&2; exit 1; }

if [ -z "$REPO" ]; then
  REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
fi

LOCK=".ops/lock"

acquire_lock() {
  if mkdir "$LOCK" 2>/dev/null; then
    echo $$ > "$LOCK/pid"
    return 0
  fi
  local pid; pid="$(cat "$LOCK/pid" 2>/dev/null || echo "")"
  if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
    echo "[oss-steward] stealing stale lock from dead pid $pid" >&2
    rm -rf "$LOCK"
    mkdir "$LOCK" && echo $$ > "$LOCK/pid" && return 0
  fi
  echo "[oss-steward] another run holds .ops/lock (pid ${pid:-?}); skipping" >&2
  return 1
}

run_once() {
  acquire_lock || return 0
  local prompt="/oss-steward:ops-run"
  if [ -n "$DRY" ]; then
    prompt="$prompt — dry run: pass --dry-run to every ops_* script and make no writes to GitHub"
  fi
  echo "[oss-steward] $(date -u +%FT%TZ) batch for $REPO${DRY:+ (dry-run)}"
  if ! claude -p "$prompt" $CLAUDE_FLAGS; then
    echo "[oss-steward] claude run failed" >&2
    rm -rf "$LOCK"
    return 1
  fi
  if [ "$DO_COMMIT" = 1 ] && [ -z "$DRY" ]; then
    git add .ops/
    git diff --cached --quiet || git commit -m "ops: run $(date -u +%Y-%m-%dT%H:%MZ)"
    if [ "$DO_PUSH" = 1 ]; then
      git pull --rebase --autostash || true
      git push
    fi
  fi
  rm -rf "$LOCK"
}

to_seconds() {
  case "$1" in
    *h) echo $(( ${1%h} * 3600 ));;
    *m) echo $(( ${1%m} * 60 ));;
    *s) echo "${1%s}";;
    *)  echo "$1";;
  esac
}

trap 'rm -rf "$LOCK"' EXIT INT TERM

if [ -n "$INTERVAL" ]; then
  SECS="$(to_seconds "$INTERVAL")"
  echo "[oss-steward] looping every ${INTERVAL} (${SECS}s); Ctrl-C to stop"
  while true; do
    run_once || true
    sleep "$SECS"
  done
else
  run_once
fi
