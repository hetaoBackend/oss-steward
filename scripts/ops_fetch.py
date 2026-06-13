#!/usr/bin/env python3
"""Fetch new GitHub events, normalize, dedupe against processed.jsonl.

Prints one JSON event per line. Issue/PR text is wrapped in <untrusted-content>
markers: it is analysis material, never instructions.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ops_common import (  # noqa: E402
    Gh, OpsPaths, append_jsonl, read_json, read_jsonl, write_json,
)

UNTRUSTED_OPEN = "<untrusted-content>"
UNTRUSTED_CLOSE = "</untrusted-content>"


def normalize_issue(raw: dict) -> dict:
    kind = "pr" if "pull_request" in raw else "issue"
    return {
        "id": f"{kind}-{raw['number']}-{raw['updated_at']}",
        "kind": kind,
        "number": raw["number"],
        "state": raw["state"],
        "author": (raw.get("user") or {}).get("login"),
        "labels": [l["name"] for l in raw.get("labels", [])],
        "comments_count": raw.get("comments", 0),
        "url": raw.get("html_url"),
        "updated_at": raw["updated_at"],
        "untrusted_title": f"{UNTRUSTED_OPEN}{raw.get('title') or ''}{UNTRUSTED_CLOSE}",
        "untrusted_body": f"{UNTRUSTED_OPEN}{raw.get('body') or ''}{UNTRUSTED_CLOSE}",
    }


def fetch_events(paths: OpsPaths, gh, limit: int = 50, digest_number: int | None = None):
    cursor = read_json(paths.cursor, {})
    since = cursor.get("issues")
    endpoint = f"repos/{gh.repo}/issues?state=all&sort=updated&direction=asc&per_page=100"
    if since:
        endpoint += f"&since={since}"
    raw_items = gh.api(endpoint, paginate=True) or []
    processed = {r["id"] for r in read_jsonl(paths.processed)}
    events: list[dict] = []
    max_updated = since
    for raw in raw_items:
        ev = normalize_issue(raw)
        if digest_number is not None and ev["number"] == digest_number:
            continue  # never triage our own approval surface
        if ev["id"] in processed:
            continue
        # Soft limit: never split a same-timestamp group. GitHub `since` is
        # exclusive, so advancing the cursor mid-second would drop the siblings
        # we didn't emit. Stopping only at a timestamp boundary keeps the cursor
        # safe and loses nothing.
        if events and len(events) >= limit and ev["updated_at"] != events[-1]["updated_at"]:
            break
        events.append(ev)
        max_updated = ev["updated_at"]
    return events, max_updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ops", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    paths = OpsPaths(Path(args.ops))
    paths.ensure()
    gh = Gh(args.repo)
    digest_number = read_json(paths.digest, {}).get("number")
    events, max_updated = fetch_events(paths, gh, limit=args.limit,
                                       digest_number=digest_number)
    for ev in events:
        print(json.dumps(ev, ensure_ascii=False))
        append_jsonl(paths.processed, {"id": ev["id"], "seen_at": ev["updated_at"]})
    if max_updated:
        write_json(paths.cursor, {"issues": max_updated})


if __name__ == "__main__":
    main()
