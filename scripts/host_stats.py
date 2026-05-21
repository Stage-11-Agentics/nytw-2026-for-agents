#!/usr/bin/env python3
"""
Compute host statistics from users.json + events/*.md owner_ids.

Writes HOST-STATS.md with:
- Top hosts by event count
- Recurring co-host pairs
- New / unknown hosts (no resolved name)

Usage:
    python3 scripts/host_stats.py --events events/ --users users.json --out HOST-STATS.md
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from collections import Counter, defaultdict
from itertools import combinations


PLATFORM_ADMIN_ID = "7DFu4rITofNzKIjA7hCx"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--users", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    users = json.load(open(args.users))

    event_owners = {}  # event_id -> list[uid]
    event_titles = {}
    event_dates = {}
    event_files = {}
    for f in pathlib.Path(args.events).glob("*.md"):
        s = f.read_text(encoding="utf-8")
        eid_m = re.search(r'event_id:\s*"([^"]+)"', s)
        own_m = re.search(r"owner_ids:\s*(\[[^\]]+\])", s)
        title_m = re.search(r'title:\s*"([^"]+)"', s)
        date_m = re.search(r"date:\s*(\S+)", s)
        if not (eid_m and own_m and title_m):
            continue
        try:
            ids = [oid for oid in json.loads(own_m.group(1)) if oid != PLATFORM_ADMIN_ID]
        except json.JSONDecodeError:
            continue
        event_owners[eid_m.group(1)] = ids
        event_titles[eid_m.group(1)] = title_m.group(1)
        event_dates[eid_m.group(1)] = date_m.group(1) if date_m else ""
        event_files[eid_m.group(1)] = f.name

    # Counts
    host_event_count: Counter = Counter()
    for eid, ids in event_owners.items():
        for oid in ids:
            host_event_count[oid] += 1

    # Co-host pairs (within same event)
    pair_count: Counter = Counter()
    for eid, ids in event_owners.items():
        for a, b in combinations(sorted(set(ids)), 2):
            pair_count[(a, b)] += 1

    # Output
    out = []
    out.append("# Host Statistics — NY Tech Week 2026")
    out.append("")
    out.append(
        f"Auto-generated from `users.json` (2,047 resolved users) and `events/*.md` "
        f"owner_ids. The Partiful platform admin `{PLATFORM_ADMIN_ID}` is filtered out "
        f"of every count below."
    )
    out.append("")
    out.append(f"- **Unique non-admin hosts**: {len(host_event_count)}")
    out.append(f"- **Total host appearances** (sum across events): {sum(host_event_count.values())}")
    out.append(f"- **Events with at least one resolved host**: {len(event_owners)}")
    out.append("")

    # Top 50 hosts
    out.append("## Top 50 hosts by event count")
    out.append("")
    out.append("| # | Host | Events | Bio |")
    out.append("|---|------|--------|-----|")
    for rank, (uid, n) in enumerate(host_event_count.most_common(50), start=1):
        u = users.get(uid) or {}
        name = (u.get("name") or "").strip() or f"`{uid}`"
        bio = (u.get("bio") or "").strip().replace("|", "\\|").replace("\n", " ")[:120]
        out.append(
            f"| {rank} | [{name}](https://partiful.com/u/{uid}) | {n} | {bio} |"
        )
    out.append("")

    # Recurring co-host pairs (2+ events together)
    out.append("## Recurring co-host pairs (2+ events together)")
    out.append("")
    out.append("Pairs of hosts who co-host the same event at least twice. Excludes solo hosts.")
    out.append("")
    out.append("| Host A | Host B | Together |")
    out.append("|--------|--------|----------|")
    recurring_pairs = [(p, c) for p, c in pair_count.items() if c >= 2]
    recurring_pairs.sort(key=lambda x: (-x[1], x[0]))
    for (a, b), c in recurring_pairs[:50]:
        ua = users.get(a) or {}
        ub = users.get(b) or {}
        na = (ua.get("name") or "").strip() or f"`{a}`"
        nb = (ub.get("name") or "").strip() or f"`{b}`"
        out.append(f"| [{na}](https://partiful.com/u/{a}) | [{nb}](https://partiful.com/u/{b}) | {c} |")
    out.append("")
    out.append(f"_({len(recurring_pairs)} pairs co-host 2+ events together; top 50 shown.)_")
    out.append("")

    # Hosts with multiple events
    out.append("## Distribution: how many events does each host run?")
    out.append("")
    bucket = Counter()
    for n in host_event_count.values():
        if n == 1:
            bucket["1 event"] += 1
        elif n <= 2:
            bucket["2 events"] += 1
        elif n <= 5:
            bucket["3-5 events"] += 1
        elif n <= 10:
            bucket["6-10 events"] += 1
        else:
            bucket["11+ events"] += 1
    out.append("| Events run | # of hosts |")
    out.append("|------------|------------|")
    for label in ["1 event", "2 events", "3-5 events", "6-10 events", "11+ events"]:
        out.append(f"| {label} | {bucket.get(label, 0)} |")
    out.append("")

    # Unresolved
    unresolved = [eid for eid in host_event_count if eid not in users]
    if unresolved:
        out.append(f"## Unresolved user IDs: {len(unresolved)}")
        out.append("")
        for uid in unresolved[:20]:
            out.append(f"- `{uid}` (in {host_event_count[uid]} events)")
        out.append("")

    pathlib.Path(args.out).write_text("\n".join(out), encoding="utf-8")
    print(f"[host-stats] wrote {args.out}")
    print(f"  unique hosts: {len(host_event_count)}")
    print(f"  recurring pairs (2+): {len(recurring_pairs)}")


if __name__ == "__main__":
    main()
