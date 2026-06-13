#!/usr/bin/env python3
"""PreToolUse hook: allow only known read-only gh commands; deny everything else
that touches gh.

All GitHub *writes* must go through scripts/ops_apply.py — the deterministic
policy gate. This hook closes the bypass path at the tool-call layer with a
default-deny whitelist (far safer than blacklisting individual write verbs,
which misses gh's POST-by-default `-f`, `-XPOST`, graphql mutations, aliases,
and unknown subcommands).
"""
import json
import re
import shlex
import sys

# gh <sub> <action> read-only allowlist. Anything not listed is denied.
SAFE_ACTIONS = {
    "issue": {"list", "view", "status"},
    "pr": {"list", "view", "diff", "checks", "status"},
    "search": {"issues", "prs", "repos", "code", "commits"},
    "label": {"list"},
    "release": {"list", "view", "download"},
    "repo": {"view", "list"},
    "run": {"list", "view"},
    "auth": {"status"},
    "cache": {"list"},
}
FIELD_FLAGS = {"-f", "-F", "--field", "--raw-field", "--input"}
# Backstop for the one case shlex can't see: a token read hidden in a quoted
# command substitution (e.g. curl -H "Authorization: token $(gh auth token)").
HARD_DENY = re.compile(r"gh\s+auth\s+token", re.IGNORECASE)
DENY_REASON = ("oss-steward: this command is blocked. GitHub writes must go through "
               "scripts/ops_apply.py (the policy gate); only read-only gh commands "
               "are permitted directly.")


def _segments(command: str) -> list[str]:
    return [s.strip() for s in re.split(r"&&|\|\||[;|\n]", command) if s.strip()]


def _normalized(command: str) -> str:
    # Expose gh hidden in command substitution to the same whitelist check.
    return command.replace("$(", " ").replace("`", " ").replace(")", " ")


def _api_is_read_only(rest: list[str]) -> bool:
    if "graphql" in rest:
        return False
    method = "GET"
    for i, t in enumerate(rest):
        if t in ("-X", "--method") and i + 1 < len(rest):
            method = rest[i + 1].upper()
        elif t.startswith("-X") and len(t) > 2:
            method = t[2:].upper()
        elif t.startswith("--method="):
            method = t.split("=", 1)[1].upper()
    if method != "GET":
        return False
    return not any(t in FIELD_FLAGS or t.split("=", 1)[0] in FIELD_FLAGS for t in rest)


def _gh_segment_is_safe(segment: str) -> bool:
    try:
        tokens = shlex.split(segment)
    except ValueError:
        return False
    if "gh" not in tokens:
        return True  # not a gh command — not our concern
    gi = tokens.index("gh")
    # gh must be the executable: only leading VAR=val assignments may precede it.
    if any("=" not in t for t in tokens[:gi]):
        return False  # xargs gh / sudo gh / wrappers → deny
    rest = tokens[gi + 1:]
    non_flags = [t for t in rest if not t.startswith("-")]
    if not non_flags:
        return False
    sub = non_flags[0]
    if sub == "api":
        return _api_is_read_only(rest)
    action = non_flags[1] if len(non_flags) > 1 else None
    return action in SAFE_ACTIONS.get(sub, set())


def decide(payload: dict):
    if payload.get("tool_name") != "Bash":
        return None
    command = (payload.get("tool_input") or {}).get("command", "")
    candidates = _segments(command) + _segments(_normalized(command))
    blocked = HARD_DENY.search(command) or any(
        not _gh_segment_is_safe(seg) for seg in candidates)
    if blocked:
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
