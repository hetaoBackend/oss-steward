#!/usr/bin/env python3
"""Sync proposals with the digest issue: publish new ones as comments, read
maintainer reactions (approve / reject), execute approved proposals after
re-checking preconditions, expire old ones, refresh the digest summary."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ops_common import (  # noqa: E402
    Gh, OpsPaths, iso, load_policy, read_json, utcnow, write_json,
)
from ops_apply import execute_proposal, load_proposals  # noqa: E402

DIGEST_TITLE = "🤖 Ops Proposals"
DIGEST_MARKER = "<!-- oss-steward-digest -->"
WRITE_PERMS = {"admin", "write", "maintain"}


def ensure_digest(paths: OpsPaths, gh) -> int:
    info = read_json(paths.digest, {})
    if info.get("number"):
        return info["number"]
    body = (f"{DIGEST_MARKER}\n\nProposals from oss-steward land here as comments.\n"
            f"React 👍 on a proposal comment to approve it, 👎 to reject. "
            f"Only accounts with write access count.")
    resp = gh.api(f"repos/{gh.repo}/issues", method="POST",
                  fields={"title": DIGEST_TITLE, "body": body})
    write_json(paths.digest, {"number": resp["number"]})
    return resp["number"]


def render_proposal_comment(p: dict) -> str:
    a = p["action"]
    params = a.get("params") or {}
    lines = [f"<!-- ops-proposal:{p['id']} -->",
             f"### `{p['id']}` — `{a['action']}` on "
             f"{a['target'].get('type', 'issue')} #{a['target'].get('number')}",
             "",
             f"**Reason:** {a.get('reason', '')}"]
    if params.get("body"):
        quoted = params["body"].replace("\n", "\n> ")
        lines += ["", "**Draft:**", "", f"> {quoted}"]
    if params.get("labels"):
        lines += ["", f"**Labels:** {', '.join(params['labels'])}"]
    lines += ["", "React 👍 to approve, 👎 to reject."]
    return "\n".join(lines)


def publish_new_proposals(paths: OpsPaths, gh, digest_number: int,
                          dry_run: bool = False) -> None:
    for p in load_proposals(paths):
        if p.get("status") == "pending" and not p.get("comment_id"):
            if dry_run:
                continue
            resp = gh.api(f"repos/{gh.repo}/issues/{digest_number}/comments",
                          method="POST", fields={"body": render_proposal_comment(p)})
            p["comment_id"] = resp["id"]
            write_json(paths.proposals / f"{p['id']}.json", p)


def _reactor_has_write(gh, login: str, cache: dict) -> bool:
    if login not in cache:
        resp = gh.api(f"repos/{gh.repo}/collaborators/{login}/permission")
        cache[login] = resp.get("permission") in WRITE_PERMS
    return cache[login]


def collect_verdicts(paths: OpsPaths, gh, policy, now: datetime) -> None:
    perm_cache: dict[str, bool] = {}
    for p in load_proposals(paths):
        if p.get("status") != "pending" or not p.get("comment_id"):
            continue
        created = datetime.strptime(p["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=now.tzinfo)
        if now - created > timedelta(days=policy.expire_days):
            p["status"] = "expired"
            write_json(paths.proposals / f"{p['id']}.json", p)
            continue
        reactions = gh.api(
            f"repos/{gh.repo}/issues/comments/{p['comment_id']}/reactions") or []
        verdict = None
        for r in reactions:
            login = (r.get("user") or {}).get("login", "")
            if not login or not _reactor_has_write(gh, login, perm_cache):
                continue
            if r.get("content") == "-1":
                verdict = "rejected"
                break
            if r.get("content") == "+1":
                verdict = "approved"
        if verdict:
            p["status"] = verdict
            p["decided_at"] = iso(now)
            write_json(paths.proposals / f"{p['id']}.json", p)


def update_digest_body(paths: OpsPaths, gh, digest_number: int,
                       dry_run: bool = False) -> None:
    proposals = load_proposals(paths)
    counts: dict[str, int] = {}
    for p in proposals:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    summary = " · ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "no proposals yet"
    attention = [p for p in proposals if p["status"] in ("failed", "stale")]
    lines = [DIGEST_MARKER, "", f"**Status:** {summary}", ""]
    if attention:
        lines.append("**Needs attention:**")
        for p in attention:
            lines.append(f"- `{p['id']}` ({p['status']}): {p.get('detail', '')}")
    lines += ["", "React 👍 on a proposal comment to approve it, 👎 to reject. "
                  "Only accounts with write access count."]
    if not dry_run:
        gh.api(f"repos/{gh.repo}/issues/{digest_number}", method="PATCH",
               fields={"body": "\n".join(lines)})


def run_sync(paths: OpsPaths, gh, now: datetime | None = None,
             dry_run: bool = False) -> None:
    now = now or utcnow()
    policy = load_policy(paths.policy)
    digest_number = ensure_digest(paths, gh)
    publish_new_proposals(paths, gh, digest_number, dry_run=dry_run)
    collect_verdicts(paths, gh, policy, now)
    for p in load_proposals(paths):
        if p.get("status") == "approved":
            execute_proposal(p["id"], paths, gh, dry_run=dry_run)
    update_digest_body(paths, gh, digest_number, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ops", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    paths = OpsPaths(Path(args.ops))
    paths.ensure()
    run_sync(paths, Gh(args.repo), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
