from ops_common import write_json
from ops_stats import compute_stats, promotion_suggestions


def seed(ops, pid, action, status):
    write_json(ops.proposals / f"{pid}.json",
               {"id": pid, "status": status, "created_at": "2026-06-01T00:00:00Z",
                "action": {"action": action, "target": {}, "params": {},
                           "source_event": pid}})


def test_compute_stats(ops):
    for i in range(9):
        seed(ops, f"P{i}", "draft-reply", "executed")
    seed(ops, "P9", "draft-reply", "rejected")
    seed(ops, "Pa", "flag-duplicate", "pending")
    stats = compute_stats(ops)
    dr = stats["actions"]["draft-reply"]
    assert dr["executed"] == 9
    assert dr["rejected"] == 1
    assert dr["acceptance"] == 0.9
    assert stats["actions"]["flag-duplicate"]["pending"] == 1


def test_promotion_needs_volume_and_rate(ops):
    for i in range(9):
        seed(ops, f"P{i}", "draft-reply", "executed")
    assert promotion_suggestions(compute_stats(ops)) == []  # only 9 decided
    seed(ops, "P9", "draft-reply", "executed")
    suggestions = promotion_suggestions(compute_stats(ops))
    assert len(suggestions) == 1
    assert "draft-reply" in suggestions[0]
