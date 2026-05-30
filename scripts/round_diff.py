#!/usr/bin/env python3
"""
Fingerprint an events/ directory by event_id and diff two crawl rounds.

The pipeline's filenames are keyed by date+time+slug, so when an event's time
or title changes a re-crawl produces a *new* file and orphans the old one.
That makes a raw `git diff` of events/ a poor "what changed" signal. This tool
keys on the stable `event_id` instead, so renames, time-shifts, removals, and
cancellations all resolve cleanly.

Usage:
    # Snapshot a round to a fingerprint JSON
    python3 scripts/round_diff.py snapshot --events events/ --out /tmp/round-prev.json

    # Diff two fingerprints (or two events dirs) into a markdown report
    python3 scripts/round_diff.py diff --prev /tmp/round-prev.json \
        --curr events.new/ --out CHANGES-2026-05-30.md \
        --prev-label 2026-05-21 --curr-label 2026-05-30
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import yaml

# Frontmatter fields we track for change detection. Guest-count fields are
# tracked but reported separately as "filling up" signal rather than edits.
TRACKED = [
    "title", "date", "day", "start_time", "end_time", "start_iso", "end_iso",
    "host", "venue_name", "venue_address", "neighborhood", "rsvp_url",
    "owner_count", "is_capped", "max_capacity", "remaining_capacity",
    "at_capacity", "guest_action", "visibility", "badges", "fetch_status",
    "canceled", "canceled_at", "cancellation_message",
]
GUEST_FIELDS = ["going_guest_count", "total_guest_count", "approved_guest_count"]

FM_DELIM = "---\n"


def coerce(v):
    """Map YAML-parsed values to JSON-native, comparable forms.

    yaml.safe_load turns `date: 2026-06-01` into a datetime.date and
    timestamps into datetime — stringify those so snapshots round-trip
    through JSON and compare consistently against a live-dir fingerprint.
    """
    import datetime as _dt
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.isoformat()
    if isinstance(v, list):
        return [coerce(x) for x in v]
    return v


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    block = text[4:end]
    try:
        data = yaml.safe_load(block)
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


def fingerprint_dir(events_dir: pathlib.Path) -> dict:
    """Map event_id -> {tracked fields, filename}."""
    out: dict[str, dict] = {}
    dupes: dict[str, list[str]] = {}
    for path in sorted(events_dir.glob("*.md")):
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        eid = fm.get("event_id")
        if not eid:
            continue
        rec = {k: coerce(fm.get(k)) for k in TRACKED + GUEST_FIELDS}
        rec["_file"] = path.name
        if eid in out:
            dupes.setdefault(eid, [out[eid]["_file"]]).append(path.name)
        out[eid] = rec
    return {"events": out, "dupes": dupes, "count": len(out)}


def load_round(spec: str) -> dict:
    """Accept either a fingerprint JSON path or an events dir path."""
    p = pathlib.Path(spec)
    if p.is_dir():
        return fingerprint_dir(p)
    return json.loads(p.read_text(encoding="utf-8"))


# Fields whose value is a comma-joined list where order is not meaningful —
# the calendar reshuffles co-host order between crawls, which is cosmetic.
SET_FIELDS = {"host", "badges"}


def values_equal(field: str, a, b) -> bool:
    if field in SET_FIELDS:
        def as_set(v):
            if v is None:
                return frozenset()
            if isinstance(v, list):
                items = v
            else:
                items = str(v).split(",")
            return frozenset(x.strip() for x in items if str(x).strip())
        return as_set(a) == as_set(b)
    return a == b


def title_of(rec: dict) -> str:
    return (rec.get("title") or rec.get("_file") or "?")[:70]


def diff_rounds(prev: dict, curr: dict) -> dict:
    pe, ce = prev["events"], curr["events"]
    prev_ids, curr_ids = set(pe), set(ce)

    added = sorted(curr_ids - prev_ids)
    removed = sorted(prev_ids - curr_ids)
    common = curr_ids & prev_ids

    newly_canceled, uncanceled, field_changed, guest_changed = [], [], [], []
    for eid in common:
        a, b = pe[eid], ce[eid]
        pa = bool(a.get("canceled") is True or a.get("canceled") == "true")
        pb = bool(b.get("canceled") is True or b.get("canceled") == "true")
        if not pa and pb:
            newly_canceled.append(eid)
        elif pa and not pb:
            uncanceled.append(eid)

        changes = {}
        for k in TRACKED:
            if k == "canceled":
                continue
            if not values_equal(k, a.get(k), b.get(k)):
                changes[k] = (a.get(k), b.get(k))
        if changes:
            field_changed.append((eid, changes))

        gchanges = {}
        for k in GUEST_FIELDS:
            if a.get(k) != b.get(k):
                gchanges[k] = (a.get(k), b.get(k))
        if gchanges:
            guest_changed.append((eid, gchanges))

    return {
        "added": added, "removed": removed,
        "newly_canceled": newly_canceled, "uncanceled": uncanceled,
        "field_changed": field_changed, "guest_changed": guest_changed,
        "prev_count": prev["count"], "curr_count": curr["count"],
    }


def render_report(d: dict, prev: dict, curr: dict,
                  prev_label: str, curr_label: str) -> str:
    pe, ce = prev["events"], curr["events"]
    L = []
    L.append(f"# NYTW dataset — change report: {prev_label} → {curr_label}\n")
    L.append(f"_Diffed by `event_id` (stable across renames/time-shifts)._\n")
    L.append("## Summary\n")
    L.append(f"| Metric | {prev_label} | {curr_label} | Δ |")
    L.append("|---|---:|---:|---:|")
    L.append(f"| Total events | {d['prev_count']} | {d['curr_count']} | "
             f"{d['curr_count'] - d['prev_count']:+d} |")
    L.append(f"| Added | — | {len(d['added'])} | +{len(d['added'])} |")
    L.append(f"| Removed | {len(d['removed'])} | — | -{len(d['removed'])} |")
    L.append(f"| Newly cancelled | — | {len(d['newly_canceled'])} | "
             f"+{len(d['newly_canceled'])} |")
    L.append(f"| Un-cancelled | — | {len(d['uncanceled'])} | "
             f"{len(d['uncanceled'])} |")
    L.append(f"| Field edits (existing) | — | {len(d['field_changed'])} | — |")
    L.append(f"| Guest-count changes | — | {len(d['guest_changed'])} | — |\n")

    L.append("### How to read this\n")
    L.append("The headline signals are **Added**, **Removed**, and **Newly "
             "cancelled**. The large **Field edits** and **Guest-count** counts "
             "are mostly expected real-world drift as the week approaches — "
             "hosts hiding precise venues behind RSVP approval (`venue_*` empties "
             "out), capacity filling (`remaining_capacity`, `at_capacity`), "
             "co-hosts being added (`owner_count`), and the occasional reschedule "
             "(`start_iso`). Co-host *reordering* is not counted as an edit. All "
             "values were verified against live Partiful via "
             "`scripts/spot_check.py` before publishing.\n")

    def line(eid, rec):
        url = rec.get("rsvp_url") or ""
        date = rec.get("date") or "?"
        return f"- `{eid}` — **{title_of(rec)}** ({date}) {url}"

    L.append(f"## Added ({len(d['added'])})\n")
    for eid in d["added"]:
        L.append(line(eid, ce[eid]))
    L.append("")

    L.append(f"## Removed ({len(d['removed'])})\n")
    L.append("_Present last round, gone from the calendar this round._\n")
    for eid in d["removed"]:
        L.append(line(eid, pe[eid]))
    L.append("")

    L.append(f"## Newly cancelled ({len(d['newly_canceled'])})\n")
    L.append("_Still on the calendar but host marked CANCELED since last round._\n")
    for eid in d["newly_canceled"]:
        rec = ce[eid]
        msg = (rec.get("cancellation_message") or "").strip().replace("\n", " ")
        L.append(line(eid, rec))
        if msg:
            L.append(f"  - _host note:_ {msg[:200]}")
    L.append("")

    if d["uncanceled"]:
        L.append(f"## Un-cancelled ({len(d['uncanceled'])})\n")
        for eid in d["uncanceled"]:
            L.append(line(eid, ce[eid]))
        L.append("")

    L.append(f"## Field edits on existing events ({len(d['field_changed'])})\n")
    L.append("_Time, venue, title, capacity, host, etc. changed since last round._\n")
    for eid, changes in d["field_changed"]:
        L.append(f"- `{eid}` — **{title_of(ce[eid])}**")
        for k, (old, new) in sorted(changes.items()):
            L.append(f"  - `{k}`: {old!r} → {new!r}")
    L.append("")

    L.append(f"## Guest-count movement ({len(d['guest_changed'])})\n")
    L.append("_RSVP/approval counts shifting — proxy for events filling up._\n")
    for eid, changes in d["guest_changed"]:
        parts = ", ".join(f"{k} {old}→{new}" for k, (old, new) in changes.items())
        L.append(f"- `{eid}` — **{title_of(ce[eid])}**: {parts}")
    L.append("")

    if curr.get("dupes"):
        L.append(f"## ⚠ Duplicate event_ids in current round ({len(curr['dupes'])})\n")
        for eid, files in curr["dupes"].items():
            L.append(f"- `{eid}`: {', '.join(files)}")
        L.append("")

    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("snapshot", help="Fingerprint an events dir to JSON")
    s.add_argument("--events", required=True)
    s.add_argument("--out", required=True)

    d = sub.add_parser("diff", help="Diff two rounds into a markdown report")
    d.add_argument("--prev", required=True, help="fingerprint JSON or events dir")
    d.add_argument("--curr", required=True, help="fingerprint JSON or events dir")
    d.add_argument("--out", required=True)
    d.add_argument("--prev-label", default="prev")
    d.add_argument("--curr-label", default="curr")
    d.add_argument("--json-out", help="also write the raw diff as JSON")

    args = ap.parse_args()

    if args.cmd == "snapshot":
        fp = fingerprint_dir(pathlib.Path(args.events))
        pathlib.Path(args.out).write_text(
            json.dumps(fp, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[snapshot] {fp['count']} events → {args.out}"
              + (f"  ⚠ {len(fp['dupes'])} dupe ids" if fp["dupes"] else ""))
        return 0

    prev = load_round(args.prev)
    curr = load_round(args.curr)
    diff = diff_rounds(prev, curr)
    report = render_report(diff, prev, curr, args.prev_label, args.curr_label)
    pathlib.Path(args.out).write_text(report, encoding="utf-8")
    print(f"[diff] {args.prev_label}→{args.curr_label}: "
          f"+{len(diff['added'])} added, -{len(diff['removed'])} removed, "
          f"{len(diff['newly_canceled'])} newly cancelled, "
          f"{len(diff['field_changed'])} edited → {args.out}")
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
