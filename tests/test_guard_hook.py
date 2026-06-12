import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from guard_gh_writes import decide


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def test_denies_issue_close():
    assert decide(bash("gh issue close 5 --repo a/b"))["hookSpecificOutput"][
        "permissionDecision"] == "deny"


def test_denies_pr_merge():
    assert decide(bash("gh pr merge 9")) is not None


def test_denies_api_post():
    assert decide(bash("gh api -X POST repos/a/b/issues/1/comments -f body=hi")) is not None
    assert decide(bash("gh api --method=DELETE repos/a/b/issues/comments/5")) is not None


def test_allows_reads():
    assert decide(bash("gh issue list --repo a/b")) is None
    assert decide(bash("gh api repos/a/b/issues/1")) is None
    assert decide(bash("gh api -X GET repos/a/b/issues --paginate")) is None


def test_allows_ops_scripts():
    assert decide(bash("python3 scripts/ops_apply.py route --ops .ops --repo a/b")) is None


def test_ignores_other_tools():
    assert decide({"tool_name": "Read", "tool_input": {"file_path": "/x"}}) is None
