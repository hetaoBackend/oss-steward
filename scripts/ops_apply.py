#!/usr/bin/env python3
"""The single write gate.

Routes structured action JSON by policy:
  low risk     -> execute now + audit (with inverse op)
  medium risk  -> write proposal, await human approval
  high/unknown -> reject + audit
LLM output never bypasses this gate; risk comes from policy.yaml, never from the model.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ops_common import (  # noqa: E402
    RISK_HIGH, RISK_LOW,
    Gh, OpsPaths, append_jsonl, iso, load_policy, read_json, read_jsonl,
    utcnow, write_json,
)

COMMENT_ACTIONS = {"draft-reply", "flag-duplicate", "draft-review-comment",
                   "welcome-contributor"}
LABEL_ACTIONS = {"add-label", "remove-label"}
MAX_RETRIES = 3


def execute_action(action: dict, gh) -> dict:
    """Run the side effect. Returns audit extras including the inverse op."""
    name = action["action"]
    target = action["target"]
    params = action.get("params") or {}
    if name == "add-label":
        labels = params["labels"]
        gh.run(["issue", "edit", str(target["number"]), "--add-label", ",".join(labels)])
        return {"inverse": {"action": "remove-label", "target": target,
                            "params": {"labels": labels}}}
    if name == "remove-label":
        labels = params["labels"]
        gh.run(["issue", "edit", str(target["number"]), "--remove-label", ",".join(labels)])
        return {"inverse": {"action": "add-label", "target": target,
                            "params": {"labels": labels}}}
    if name in COMMENT_ACTIONS:
        resp = gh.api(f"repos/{gh.repo}/issues/{target['number']}/comments",
                      method="POST", fields={"body": params["body"]})
        return {"inverse": {"action": "delete-comment",
                            "target": {"comment_id": resp.get("id")}},
                "comment_id": resp.get("id")}
    if name == "suggest-assignee":
        gh.api(f"repos/{gh.repo}/issues/{target['number']}/assignees",
               method="POST", fields={"assignees[]": params["assignee"]})
        return {"inverse": {"action": "remove-assignee", "target": target,
                            "params": {"assignee": params["assignee"]}}}
    raise ValueError(f"no executor for action {name}")


def validate_params(action: dict, ap) -> str | None:
    if ap.allowed_labels is not None:
        labels = (action.get("params") or {}).get("labels", [])
        bad = [l for l in labels if l not in ap.allowed_labels]
        if bad:
            return f"labels not in whitelist: {bad}"
    if action["action"] in COMMENT_ACTIONS and not (action.get("params") or {}).get("body"):
        return "comment action requires params.body"
    return None


def _dedupe_key(rec: dict) -> tuple:
    return (rec.get("source_event"), rec.get("action"),
            json.dumps(rec.get("target"), sort_keys=True, ensure_ascii=False))


def already_executed(paths: OpsPaths, action: dict) -> bool:
    key = _dedupe_key(action)
    for f in sorted(paths.audit_dir.glob("*.jsonl")):
        for rec in read_jsonl(f):
            if rec.get("status") == "executed" and _dedupe_key(rec) == key:
                return True
    return False


def load_proposals(paths: OpsPaths) -> list[dict]:
    return sorted(
        (read_json(p, {}) for p in paths.proposals.glob("*.json")),
        key=lambda p: p.get("created_at", ""),
    )


def route_action(action: dict, policy, paths: OpsPaths, gh, dry_run: bool = False) -> dict:
    now = utcnow()
    name = action.get("action", "")

    def audit(status: str, detail: str | None = None, extra: dict | None = None) -> dict:
        rec = {"ts": iso(now), "action": name, "target": action.get("target"),
               "params": action.get("params"), "source_event": action.get("source_event"),
               "status": status, "detail": detail, "dry_run": dry_run}
        if extra:
            rec.update(extra)
        append_jsonl(paths.audit_file(now), rec)
        return rec

    ap = policy.actions.get(name)
    if ap is None:
        return audit("rejected", f"unknown action {name!r}: policy default is reject")
    if ap.risk == RISK_HIGH:
        return audit("rejected", "high-risk action: human only")
    err = validate_params(action, ap)
    if err:
        return audit("rejected", err)

    if ap.risk == RISK_LOW:
        if already_executed(paths, action):
            return audit("skipped", "duplicate of an already-executed action")
        if dry_run:
            return audit("executed", "dry-run: side effect skipped")
        try:
            extra = execute_action(action, gh)
        except Exception as exc:  # noqa: BLE001 — a failed write is audited, not raised
            return audit("failed", str(exc))
        return audit("executed", None, extra)

    # medium risk -> proposal
    pending = [p for p in load_proposals(paths) if p.get("status") == "pending"]
    if len(pending) >= policy.max_pending:
        return audit("rejected", f"max-pending ({policy.max_pending}) reached")
    pid = "P" + uuid.uuid4().hex[:8]
    proposal = {"id": pid, "status": "pending", "created_at": iso(now),
                "action": action, "comment_id": None, "retries": 0}
    write_json(paths.proposals / f"{pid}.json", proposal)
    return audit("proposed", pid)


def check_preconditions(action: dict, gh) -> str | None:
    """Return a reason string if drifted, None if still valid."""
    pre = action.get("preconditions") or {}
    if not pre:
        return None
    target = action["target"]
    issue = gh.api(f"repos/{gh.repo}/issues/{target['number']}")
    if "state" in pre and issue.get("state") != pre["state"]:
        return f"state changed to {issue.get('state')!r}"
    # Label drift only invalidates label actions. The steward's own labeling of an
    # issue (a separate low-risk action in the same run) must not make a queued
    # reply/review/assignee proposal for that issue go stale.
    if "labels_snapshot" in pre and action["action"] in LABEL_ACTIONS:
        current = sorted(l["name"] for l in issue.get("labels", []))
        if current != sorted(pre["labels_snapshot"]):
            return "labels changed since proposal"
    if "comments_count" in pre and issue.get("comments", 0) != pre["comments_count"]:
        return "new comments since proposal"
    return None


def execute_proposal(pid: str, paths: OpsPaths, gh, dry_run: bool = False) -> dict:
    now = utcnow()
    path = paths.proposals / f"{pid}.json"
    proposal = read_json(path, None)
    if proposal is None:
        return {"status": "error", "detail": f"proposal {pid} not found"}
    if proposal.get("status") != "approved":
        return {"status": "error",
                "detail": f"proposal {pid} is {proposal.get('status')!r}, not approved"}

    def audit(status, detail=None, extra=None):
        rec = {"ts": iso(now), "proposal": pid,
               "action": proposal["action"]["action"],
               "target": proposal["action"].get("target"),
               "params": proposal["action"].get("params"),
               "source_event": proposal["action"].get("source_event"),
               "status": status, "detail": detail, "dry_run": dry_run}
        if extra:
            rec.update(extra)
        append_jsonl(paths.audit_file(now), rec)

    reason = check_preconditions(proposal["action"], gh)
    if reason:
        proposal["status"] = "stale"
        proposal["detail"] = reason
        audit("stale", reason)
    else:
        try:
            extra = {} if dry_run else execute_action(proposal["action"], gh)
            proposal["status"] = "executed"
            proposal["executed_at"] = iso(now)
            audit("executed", None, extra)
        except Exception as exc:  # noqa: BLE001 — any executor failure is retryable
            proposal["retries"] = proposal.get("retries", 0) + 1
            if proposal["retries"] >= MAX_RETRIES:
                proposal["status"] = "failed"
                proposal["detail"] = str(exc)
                audit("failed", str(exc))
            else:
                audit("retry", str(exc))
    write_json(path, proposal)
    return proposal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("route", help="route one action JSON (stdin or --file)")
    r.add_argument("--ops", required=True)
    r.add_argument("--repo", required=True)
    r.add_argument("--file")
    r.add_argument("--dry-run", action="store_true")
    e = sub.add_parser("execute-proposal", help="execute an approved proposal")
    e.add_argument("--ops", required=True)
    e.add_argument("--repo", required=True)
    e.add_argument("--id", required=True)
    e.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    paths = OpsPaths(Path(args.ops))
    paths.ensure()
    gh = Gh(args.repo)

    if args.cmd == "route":
        policy = load_policy(paths.policy)
        raw = Path(args.file).read_text() if args.file else sys.stdin.read()
        result = route_action(json.loads(raw), policy, paths, gh, dry_run=args.dry_run)
    else:
        result = execute_proposal(args.id, paths, gh, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
