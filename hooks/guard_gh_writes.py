#!/usr/bin/env python3
"""PreToolUse hook: deny direct gh write commands.

All GitHub writes must go through scripts/ops_apply.py — the deterministic
policy gate. This hook closes the bypass path at the tool-call layer."""
import json
import re
import sys

WRITE_PATTERNS = [
    r"\bgh\s+issue\s+(close|reopen|edit|comment|create|delete|transfer|lock|unlock|pin|unpin)\b",
    r"\bgh\s+pr\s+(close|reopen|edit|comment|create|merge|review|ready|lock|unlock)\b",
    r"\bgh\s+api\b[^|;&]*(-X|--method)[=\s]+(POST|PATCH|PUT|DELETE)\b",
    r"\bgh\s+(release|label)\s+(create|edit|delete|upload)\b",
    r"\bgh\s+repo\s+(delete|edit|archive|unarchive|rename)\b",
]
DENY_REASON = ("oss-steward: direct gh write commands are blocked. All writes must "
               "go through scripts/ops_apply.py (the policy gate).")


def decide(payload: dict):
    if payload.get("tool_name") != "Bash":
        return None
    command = (payload.get("tool_input") or {}).get("command", "")
    for pat in WRITE_PATTERNS:
        if re.search(pat, command, re.IGNORECASE):
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": DENY_REASON,
            }}
    return None


def main() -> None:
    result = decide(json.load(sys.stdin))
    if result:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
