from ops_common import load_policy, read_jsonl, append_jsonl, read_json, write_json


def test_load_policy(ops):
    policy = load_policy(ops.policy)
    assert policy.actions["add-label"].risk == "low"
    assert "bug" in policy.actions["add-label"].allowed_labels
    assert policy.actions["draft-reply"].risk == "medium"
    assert policy.actions["draft-reply"].allowed_labels is None
    assert policy.actions["close-issue"].risk == "high"
    assert policy.unknown_action == "reject"
    assert policy.expire_days == 14
    assert policy.max_pending == 30


def test_jsonl_roundtrip(tmp_path):
    p = tmp_path / "a.jsonl"
    assert read_jsonl(p) == []
    append_jsonl(p, {"x": 1})
    append_jsonl(p, {"x": 2})
    assert read_jsonl(p) == [{"x": 1}, {"x": 2}]


def test_json_roundtrip(tmp_path):
    p = tmp_path / "nested" / "b.json"
    assert read_json(p, {}) == {}
    write_json(p, {"k": "v"})
    assert read_json(p, {}) == {"k": "v"}


def test_ops_paths(ops):
    assert ops.proposals.is_dir()
    assert ops.audit_dir.is_dir()
    assert ops.policy.name == "policy.yaml"
