from ops_common import write_json, read_json
from ops_apply import execute_proposal


def issue_resp(state="open", labels=(), comments=1):
    return {"state": state, "labels": [{"name": l} for l in labels], "comments": comments}


def make_proposal(ops, status="approved", preconditions=None):
    action = {
        "action": "draft-reply",
        "target": {"type": "issue", "number": 7},
        "params": {"body": "Thanks! Could you share the full stack trace?"},
        "reason": "needs more info",
        "source_event": "issue-7-x",
    }
    if preconditions is not None:
        action["preconditions"] = preconditions
    p = {"id": "Pabc12345", "status": status, "created_at": "2026-06-13T00:00:00Z",
         "action": action, "comment_id": 555, "retries": 0}
    write_json(ops.proposals / "Pabc12345.json", p)
    return p


def test_executes_approved_proposal(ops, gh):
    gh.api_responses[("GET", "repos/acme/widget/issues/7")] = issue_resp(comments=1)
    gh.api_responses[("POST", "repos/acme/widget/issues/7/comments")] = {"id": 999}
    make_proposal(ops, preconditions={"state": "open", "comments_count": 1})
    result = execute_proposal("Pabc12345", ops, gh)
    assert result["status"] == "executed"
    saved = read_json(ops.proposals / "Pabc12345.json", {})
    assert saved["status"] == "executed"


def test_stale_when_state_changed(ops, gh):
    gh.api_responses[("GET", "repos/acme/widget/issues/7")] = issue_resp(state="closed")
    make_proposal(ops, preconditions={"state": "open"})
    result = execute_proposal("Pabc12345", ops, gh)
    assert result["status"] == "stale"
    assert all(c[1] != "POST" for c in gh.calls if c[0] == "api")


def test_stale_when_new_comments(ops, gh):
    gh.api_responses[("GET", "repos/acme/widget/issues/7")] = issue_resp(comments=5)
    make_proposal(ops, preconditions={"state": "open", "comments_count": 1})
    assert execute_proposal("Pabc12345", ops, gh)["status"] == "stale"


def test_label_drift_does_not_stale_a_reply(ops, gh):
    # The steward's own labeling of #7 must not invalidate a queued draft-reply.
    gh.api_responses[("GET", "repos/acme/widget/issues/7")] = issue_resp(
        labels=["question"], comments=0)
    gh.api_responses[("POST", "repos/acme/widget/issues/7/comments")] = {"id": 999}
    make_proposal(ops, preconditions={"state": "open", "labels_snapshot": [],
                                       "comments_count": 0})
    result = execute_proposal("Pabc12345", ops, gh)
    assert result["status"] == "executed"


def test_rejects_unapproved(ops, gh):
    make_proposal(ops, status="pending")
    result = execute_proposal("Pabc12345", ops, gh)
    assert result["status"] == "error"


def test_failure_increments_retries_then_fails(ops, gh):
    gh.api_responses[("GET", "repos/acme/widget/issues/7")] = issue_resp(comments=1)

    def boom(endpoint, method="GET", fields=None, paginate=False):
        gh.calls.append(("api", method, endpoint, fields or {}))
        if method == "POST":
            raise RuntimeError("rate limited")
        return gh.api_responses.get((method, endpoint), {})

    gh.api = boom
    make_proposal(ops, preconditions={"state": "open", "comments_count": 1})
    for expected_retries in (1, 2):
        result = execute_proposal("Pabc12345", ops, gh)
        assert result["status"] == "approved"
        assert result["retries"] == expected_retries
    result = execute_proposal("Pabc12345", ops, gh)
    assert result["status"] == "failed"
