import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from ops_common import OpsPaths  # noqa: E402

POLICY_YAML = """\
version: 1
actions:
  add-label:
    risk: low
    allowed-labels: [bug, enhancement, question, documentation, good-first-issue]
  remove-label:
    risk: low
    allowed-labels: [bug, enhancement, question, documentation, good-first-issue]
  draft-reply:
    risk: medium
  flag-duplicate:
    risk: medium
  draft-review-comment:
    risk: medium
  suggest-assignee:
    risk: medium
  close-issue:
    risk: high
  merge-pr:
    risk: high
defaults:
  unknown-action: reject
proposal:
  expire-days: 14
  max-pending: 30
"""


class FakeGh:
    """Records every call; returns canned responses keyed by (method, endpoint)."""

    def __init__(self, repo="acme/widget", api_responses=None):
        self.repo = repo
        self.calls = []
        self.api_responses = dict(api_responses or {})

    def api(self, endpoint, method="GET", fields=None, paginate=False):
        self.calls.append(("api", method, endpoint, fields or {}))
        return self.api_responses.get((method, endpoint), {})

    def run(self, args):
        self.calls.append(("run", tuple(args)))
        return ""


@pytest.fixture
def ops(tmp_path):
    paths = OpsPaths(tmp_path / ".ops")
    paths.ensure()
    paths.policy.write_text(POLICY_YAML)
    return paths


@pytest.fixture
def gh():
    return FakeGh()
