import json

from ops_common import load_policy, read_jsonl
from ops_apply import route_action, load_proposals


def make_action(**over):
    a = {
        "action": "add-label",
        "target": {"type": "issue", "number": 123},
        "params": {"labels": ["bug"]},
        "reason": "stack trace points to a crash",
        "source_event": "issue-123-2026-06-13T01:00:00Z",
        "preconditions": {"state": "open"},
    }
    a.update(over)
    return a


def audit_records(ops):
    recs = []
    for f in sorted(ops.audit_dir.glob("*.jsonl")):
        recs += read_jsonl(f)
    return recs


def test_low_risk_executes(ops, gh):
    policy = load_policy(ops.policy)
    result = route_action(make_action(), policy, ops, gh)
    assert result["status"] == "executed"
    assert ("run", ("issue", "edit", "123", "--add-label", "bug")) in gh.calls
    recs = audit_records(ops)
    assert recs[-1]["status"] == "executed"
    assert recs[-1]["inverse"]["action"] == "remove-label"


def test_low_risk_dry_run_does_not_call_gh(ops, gh):
    policy = load_policy(ops.policy)
    result = route_action(make_action(), policy, ops, gh, dry_run=True)
    assert result["status"] == "executed"
    assert gh.calls == []


def test_label_whitelist_rejects(ops, gh):
    policy = load_policy(ops.policy)
    result = route_action(make_action(params={"labels": ["urgent!!"]}), policy, ops, gh)
    assert result["status"] == "rejected"
    assert "whitelist" in result["detail"]
    assert gh.calls == []


def test_medium_risk_creates_proposal(ops, gh):
    policy = load_policy(ops.policy)
    action = make_action(action="draft-reply", params={"body": "Thanks for the report!"})
    result = route_action(action, policy, ops, gh)
    assert result["status"] == "proposed"
    proposals = load_proposals(ops)
    assert len(proposals) == 1
    assert proposals[0]["status"] == "pending"
    assert proposals[0]["action"]["action"] == "draft-reply"
    assert gh.calls == []


def test_high_risk_rejected(ops, gh):
    policy = load_policy(ops.policy)
    result = route_action(make_action(action="close-issue", params={}), policy, ops, gh)
    assert result["status"] == "rejected"
    assert "human" in result["detail"]
    assert gh.calls == []


def test_unknown_action_rejected(ops, gh):
    policy = load_policy(ops.policy)
    result = route_action(make_action(action="delete-repo", params={}), policy, ops, gh)
    assert result["status"] == "rejected"
    assert gh.calls == []


def test_idempotent_low_risk(ops, gh):
    policy = load_policy(ops.policy)
    route_action(make_action(), policy, ops, gh)
    result = route_action(make_action(), policy, ops, gh)
    assert result["status"] == "skipped"
    assert len([c for c in gh.calls if c[0] == "run"]) == 1


def test_max_pending_blocks_new_proposals(ops, gh):
    policy = load_policy(ops.policy)
    policy.max_pending = 2
    for i in range(2):
        route_action(
            make_action(action="draft-reply", params={"body": "hi"},
                        source_event=f"issue-{i}-x"),
            policy, ops, gh)
    result = route_action(
        make_action(action="draft-reply", params={"body": "hi"}, source_event="issue-9-x"),
        policy, ops, gh)
    assert result["status"] == "rejected"
    assert "max-pending" in result["detail"]
