from datetime import datetime, timezone

from ops_common import load_policy, read_json, write_json
from ops_sync import (
    ensure_digest, publish_new_proposals, collect_verdicts, run_sync,
    render_proposal_comment,
)

NOW = datetime(2026, 6, 13, 2, 0, tzinfo=timezone.utc)


def seed_proposal(ops, pid="P1", status="pending", comment_id=None,
                  created_at="2026-06-13T00:00:00Z", action_name="draft-reply"):
    p = {"id": pid, "status": status, "created_at": created_at,
         "comment_id": comment_id, "retries": 0,
         "action": {"action": action_name, "target": {"type": "issue", "number": 7},
                    "params": {"body": "Thanks!"}, "reason": "be nice",
                    "source_event": f"issue-7-{pid}",
                    "preconditions": {"state": "open"}}}
    write_json(ops.proposals / f"{pid}.json", p)
    return p


def test_ensure_digest_creates_once(ops, gh):
    gh.api_responses[("POST", "repos/acme/widget/issues")] = {"number": 42}
    assert ensure_digest(ops, gh) == 42
    assert ensure_digest(ops, gh) == 42
    posts = [c for c in gh.calls if c[0] == "api" and c[1] == "POST"]
    assert len(posts) == 1


def test_render_includes_marker_and_draft():
    p = {"id": "P1", "action": {"action": "draft-reply",
                                "target": {"type": "issue", "number": 7},
                                "params": {"body": "line1\nline2"}, "reason": "r"}}
    body = render_proposal_comment(p)
    assert "<!-- ops-proposal:P1 -->" in body
    assert "> line1" in body and "> line2" in body


def test_publish_attaches_comment_id(ops, gh):
    seed_proposal(ops)
    gh.api_responses[("POST", "repos/acme/widget/issues/42/comments")] = {"id": 777}
    publish_new_proposals(ops, gh, 42)
    assert read_json(ops.proposals / "P1.json", {})["comment_id"] == 777


def test_collect_verdicts_approval_requires_write_permission(ops, gh):
    seed_proposal(ops, comment_id=777)
    gh.api_responses[("GET", "repos/acme/widget/issues/comments/777/reactions")] = [
        {"content": "+1", "user": {"login": "rando"}},
    ]
    gh.api_responses[("GET", "repos/acme/widget/collaborators/rando/permission")] = {
        "permission": "read"}
    policy = load_policy(ops.policy)
    collect_verdicts(ops, gh, policy, NOW)
    assert read_json(ops.proposals / "P1.json", {})["status"] == "pending"


def test_collect_verdicts_maintainer_approves(ops, gh):
    seed_proposal(ops, comment_id=777)
    gh.api_responses[("GET", "repos/acme/widget/issues/comments/777/reactions")] = [
        {"content": "+1", "user": {"login": "alice"}},
    ]
    gh.api_responses[("GET", "repos/acme/widget/collaborators/alice/permission")] = {
        "permission": "admin"}
    policy = load_policy(ops.policy)
    collect_verdicts(ops, gh, policy, NOW)
    assert read_json(ops.proposals / "P1.json", {})["status"] == "approved"


def test_collect_verdicts_reject_wins(ops, gh):
    seed_proposal(ops, comment_id=777)
    gh.api_responses[("GET", "repos/acme/widget/issues/comments/777/reactions")] = [
        {"content": "+1", "user": {"login": "alice"}},
        {"content": "-1", "user": {"login": "alice"}},
    ]
    gh.api_responses[("GET", "repos/acme/widget/collaborators/alice/permission")] = {
        "permission": "admin"}
    policy = load_policy(ops.policy)
    collect_verdicts(ops, gh, policy, NOW)
    assert read_json(ops.proposals / "P1.json", {})["status"] == "rejected"


def test_collect_verdicts_expires_old(ops, gh):
    seed_proposal(ops, comment_id=777, created_at="2026-05-01T00:00:00Z")
    gh.api_responses[("GET", "repos/acme/widget/issues/comments/777/reactions")] = []
    policy = load_policy(ops.policy)
    collect_verdicts(ops, gh, policy, NOW)
    assert read_json(ops.proposals / "P1.json", {})["status"] == "expired"


def test_run_sync_executes_approved(ops, gh):
    seed_proposal(ops, status="approved", comment_id=777)
    gh.api_responses[("GET", "repos/acme/widget/issues/7")] = {
        "state": "open", "labels": [], "comments": 0}
    gh.api_responses[("POST", "repos/acme/widget/issues/7/comments")] = {"id": 888}
    gh.api_responses[("POST", "repos/acme/widget/issues")] = {"number": 42}
    run_sync(ops, gh, now=NOW)
    assert read_json(ops.proposals / "P1.json", {})["status"] == "executed"
