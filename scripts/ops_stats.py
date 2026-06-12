#!/usr/bin/env python3
"""Aggregate proposal outcomes into stats.json and print promotion suggestions.

A suggestion is advice for the maintainer to edit policy.yaml by hand;
the agent never promotes an action's risk tier itself."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ops_common import OpsPaths, iso, utcnow, write_json  # noqa: E402
from ops_apply import load_proposals  # noqa: E402

DECIDED = ("executed", "rejected", "expired", "failed", "stale")
PROMOTE_MIN_DECIDED = 10
PROMOTE_MIN_ACCEPTANCE = 0.95


def compute_stats(paths: OpsPaths) -> dict:
    actions: dict[str, dict] = {}
    for p in load_proposals(paths):
        name = p["action"]["action"]
        bucket = actions.setdefault(name, {})
        bucket[p["status"]] = bucket.get(p["status"], 0) + 1
    for bucket in actions.values():
        decided = sum(bucket.get(s, 0) for s in DECIDED)
        bucket["decided"] = decided
        bucket["acceptance"] = (
            round(bucket.get("executed", 0) / decided, 3) if decided else None)
    return {"generated_at": iso(utcnow()), "actions": actions}


def promotion_suggestions(stats: dict) -> list[str]:
    out = []
    for name, bucket in stats["actions"].items():
        if (bucket["decided"] >= PROMOTE_MIN_DECIDED
                and (bucket["acceptance"] or 0) >= PROMOTE_MIN_ACCEPTANCE):
            out.append(
                f"`{name}`: {bucket['decided']} decided, "
                f"acceptance {bucket['acceptance']:.0%} — consider promoting to "
                f"risk: low in .ops/policy.yaml (maintainer decision).")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ops", required=True)
    args = parser.parse_args()
    paths = OpsPaths(Path(args.ops))
    paths.ensure()
    stats = compute_stats(paths)
    write_json(paths.stats, stats)
    print(json.dumps({"stats": stats,
                      "suggestions": promotion_suggestions(stats)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
