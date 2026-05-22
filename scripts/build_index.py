#!/usr/bin/env python3
"""
Build INDEX.md from events/*.md frontmatter.

Usage:
    python3 scripts/build_index.py --events events/ --out INDEX.md
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import defaultdict, Counter

FRONTMATTER_RE = re.compile(r"^---\n(.+?)\n---", re.S)


def parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    block = m.group(1)
    fm = {}
    for line in block.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if v.startswith('"') and v.endswith('"'):
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                v = v.strip('"')
        elif v.startswith("["):
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                pass
        elif v in ("true", "false"):
            v = v == "true"
        fm[k] = v
    return fm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    events_dir = pathlib.Path(args.events)
    files = sorted(events_dir.glob("*.md"))
    files = [f for f in files if not f.name.startswith("_")]

    rows = []
    for f in files:
        fm = parse_frontmatter(f.read_text(encoding="utf-8"))
        if not fm:
            continue
        fm["_file"] = f.name
        rows.append(fm)

    # Sort by date then start_time
    def sort_key(r):
        return (r.get("date") or "9999-99-99", r.get("start_iso") or "")

    rows.sort(key=sort_key)

    # Buckets
    by_day = defaultdict(list)
    by_host = defaultdict(list)
    by_neighborhood = defaultdict(list)
    by_badge = defaultdict(list)
    failed_or_stub = []
    cancelled = []

    for r in rows:
        day = r.get("date", "unknown")
        by_day[day].append(r)
        h = r.get("host") or "Unknown host"
        by_host[h].append(r)
        n = r.get("neighborhood") or "Unknown"
        by_neighborhood[n].append(r)
        for b in r.get("badges", []) or []:
            by_badge[b].append(r)
        if r.get("fetch_status") not in (None, "ok"):
            failed_or_stub.append(r)
        if r.get("canceled") is True or r.get("canceled") == "true":
            cancelled.append(r)

    out = []
    out.append("# NY Tech Week 2026 — Index")
    out.append("")
    out.append(
        f"Auto-generated from `events/*.md` frontmatter. "
        f"{len(rows)} events. See `README.md` for schema."
    )
    out.append("")

    # Summary stats
    out.append("## Summary")
    out.append("")
    out.append(f"- **Total events:** {len(rows)}")
    out.append(f"- **Live events:** {len(rows) - len(cancelled)}")
    out.append(f"- **Cancelled events:** {len(cancelled)} (see `## Cancelled` at bottom)")
    out.append(f"- **Days covered:** {len(by_day)}")
    out.append(f"- **Unique hosts:** {len(by_host)}")
    out.append(f"- **Unique neighborhoods:** {len(by_neighborhood)}")
    if failed_or_stub:
        out.append(
            f"- **Events with incomplete data:** {len(failed_or_stub)} "
            f"(see `## Incomplete fetches` at bottom)"
        )
    out.append("")

    # Day-by-day
    out.append("## By day")
    out.append("")
    day_labels = {
        "2026-06-01": "Monday, June 1",
        "2026-06-02": "Tuesday, June 2",
        "2026-06-03": "Wednesday, June 3",
        "2026-06-04": "Thursday, June 4",
        "2026-06-05": "Friday, June 5",
        "2026-06-06": "Saturday, June 6",
        "2026-06-07": "Sunday, June 7",
    }
    for day in sorted(by_day.keys()):
        label = day_labels.get(day, day)
        events = by_day[day]
        out.append(f"### {label} — {len(events)} events")
        out.append("")
        # Live first, cancelled bumped to the end of each day with a ❌ marker.
        live_first = sorted(events, key=lambda r: (1 if (r.get("canceled") is True or r.get("canceled") == "true") else 0, r.get("start_iso") or ""))
        for r in live_first:
            time = r.get("start_time", "").replace(" ET", "")
            title = r.get("title", "(untitled)")
            host = r.get("host", "")
            nbhd = r.get("neighborhood", "")
            fname = r["_file"]
            is_cancelled = r.get("canceled") is True or r.get("canceled") == "true"
            line_parts = [f"`{time:>8}`" if time else "          "]
            if is_cancelled:
                line_parts.append(f"❌ ~~[{title}](events/{fname})~~")
            else:
                line_parts.append(f"[{title}](events/{fname})")
            meta = []
            if host:
                meta.append(host)
            if nbhd:
                meta.append(nbhd)
            if meta:
                line_parts.append(f"— *{' · '.join(meta)}*")
            out.append("- " + " ".join(line_parts))
        out.append("")

    # Top hosts (events with 3+ entries get a section)
    out.append("## Hosts running multiple events")
    out.append("")
    multi_host = sorted(
        [(h, evs) for h, evs in by_host.items() if len(evs) >= 3],
        key=lambda x: (-len(x[1]), x[0]),
    )
    if multi_host:
        for h, evs in multi_host[:50]:
            out.append(f"### {h} — {len(evs)} events")
            out.append("")
            for r in evs:
                date = r.get("date", "")
                time = r.get("start_time", "").replace(" ET", "")
                title = r.get("title", "(untitled)")
                fname = r["_file"]
                out.append(f"- `{date} {time}` [{title}](events/{fname})")
            out.append("")
    else:
        out.append("_None found._")
        out.append("")

    # Neighborhoods
    out.append("## By neighborhood")
    out.append("")
    for nbhd in sorted(by_neighborhood.keys()):
        evs = by_neighborhood[nbhd]
        out.append(f"- **{nbhd}** — {len(evs)} events")
    out.append("")

    # Badges
    out.append("## By badge / track")
    out.append("")
    for badge in sorted(by_badge.keys()):
        evs = by_badge[badge]
        out.append(f"- **{badge}** — {len(evs)} events")
    out.append("")

    # Cancelled
    if cancelled:
        out.append("## Cancelled")
        out.append("")
        out.append(
            f"{len(cancelled)} events the hosts marked CANCELED on Partiful. "
            "Kept in the dataset so the URLs stay resolvable and downstream "
            "agents can see what was cancelled (and why)."
        )
        out.append("")
        cancelled.sort(key=lambda r: (r.get("date") or "", r.get("start_iso") or ""))
        for r in cancelled:
            date = r.get("date", "")
            time = r.get("start_time", "").replace(" ET", "")
            title = r.get("title", "(untitled)")
            host = r.get("host", "")
            out.append(
                f"- `{date} {time}` ~~[{title}](events/{r['_file']})~~"
                + (f" — *{host}*" if host else "")
            )
        out.append("")

    # Incomplete
    if failed_or_stub:
        out.append("## Incomplete fetches")
        out.append("")
        out.append(
            "These events couldn't be fully fetched from Partiful at crawl time. "
            "Their files contain manifest-derived data only; follow the RSVP link for full detail."
        )
        out.append("")
        for r in failed_or_stub:
            out.append(f"- [{r.get('title', '?')}](events/{r['_file']}) — {r.get('rsvp_url', '')}")
        out.append("")

    pathlib.Path(args.out).write_text("\n".join(out), encoding="utf-8")
    print(f"[index] wrote {args.out} with {len(rows)} events")


if __name__ == "__main__":
    main()
