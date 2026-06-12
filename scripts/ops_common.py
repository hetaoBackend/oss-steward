"""Shared helpers for oss-steward ops scripts: policy, state paths, jsonl, gh wrapper."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"


@dataclass
class ActionPolicy:
    risk: str
    allowed_labels: list[str] | None = None


@dataclass
class Policy:
    actions: dict[str, ActionPolicy]
    unknown_action: str = "reject"
    expire_days: int = 14
    max_pending: int = 30


def load_policy(path: Path) -> Policy:
    raw = yaml.safe_load(Path(path).read_text())
    actions = {}
    for name, spec in (raw.get("actions") or {}).items():
        actions[name] = ActionPolicy(
            risk=spec["risk"],
            allowed_labels=spec.get("allowed-labels"),
        )
    defaults = raw.get("defaults") or {}
    proposal = raw.get("proposal") or {}
    return Policy(
        actions=actions,
        unknown_action=defaults.get("unknown-action", "reject"),
        expire_days=int(proposal.get("expire-days", 14)),
        max_pending=int(proposal.get("max-pending", 30)),
    )


@dataclass
class OpsPaths:
    root: Path

    @property
    def policy(self) -> Path:
        return self.root / "policy.yaml"

    @property
    def cursor(self) -> Path:
        return self.root / "cursor.json"

    @property
    def processed(self) -> Path:
        return self.root / "processed.jsonl"

    @property
    def proposals(self) -> Path:
        return self.root / "proposals"

    @property
    def audit_dir(self) -> Path:
        return self.root / "audit"

    @property
    def stats(self) -> Path:
        return self.root / "stats.json"

    @property
    def digest(self) -> Path:
        return self.root / "digest.json"

    def audit_file(self, now: datetime) -> Path:
        return self.audit_dir / f"{now:%Y-%m}.jsonl"

    def ensure(self) -> None:
        self.proposals.mkdir(parents=True, exist_ok=True)
        self.audit_dir.mkdir(parents=True, exist_ok=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def read_jsonl(path: Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def append_jsonl(path: Path, obj: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_json(path: Path, default):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text())


def write_json(path: Path, obj) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


class Gh:
    """Thin wrapper over the gh CLI. All GitHub access goes through here."""

    def __init__(self, repo: str):
        self.repo = repo

    def api(self, endpoint: str, method: str = "GET",
            fields: dict | None = None, paginate: bool = False):
        cmd = ["gh", "api", "-X", method, endpoint]
        if paginate:
            cmd.append("--paginate")
        for k, v in (fields or {}).items():
            cmd += ["-f", f"{k}={v}"]
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
        return json.loads(out) if out.strip() else {}

    def run(self, args: list[str]) -> str:
        cmd = ["gh"] + list(args) + ["--repo", self.repo]
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
