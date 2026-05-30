#!/usr/bin/env python3
"""
Spot-check the dataset against live Partiful pages.

Samples events (across categories: newly-added, cancelled, at-capacity, plus
random) and re-fetches each one's live Partiful __NEXT_DATA__, comparing the
stored frontmatter against what the source says *right now*. Structural fields
(title, start time, venue, cancelled, capacity flags) must match; guest counts
are reported but treated as soft (they drift in real time).

Usage:
    python3 scripts/spot_check.py --events events.new/ --sample 24 \
        --added-ids .recrawl/added.txt --out .recrawl/spot-check.md
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import sys
import urllib.request

import yaml

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15")
NEXT_DATA_RE = re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>', re.S)

# Structural fields: a mismatch here is a real problem.
HARD = ["title", "start_iso", "venue_name", "canceled", "at_capacity", "is_capped"]
# Soft fields: real-time drift between our enrich and now is expected.
SOFT = ["owner_count", "going_guest_count", "total_guest_count", "remaining_capacity"]


def parse_fm(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    block = text[4:end] if end != -1 else ""
    try:
        d = yaml.safe_load(block)
        return d if isinstance(d, dict) else {}
    except yaml.YAMLError:
        return {}


def fetch_live(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="replace")
    m = NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))["props"]["pageProps"]["event"]
    except (json.JSONDecodeError, KeyError):
        return None


def norm(v):
    if isinstance(v, bool):
        return v
    if v in (None, ""):
        return None
    import datetime as _dt
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.isoformat()
    return str(v).strip()


def live_fields(ev: dict) -> dict:
    title = re.sub(r"\s*-?\s*#NYTechWeek\s*$", "", (ev.get("title") or "").strip())
    loc = (ev.get("locationInfo") or {}).get("mapsInfo") or {}
    owners = ev.get("owners") or []
    return {
        "title": title,
        "start_iso": ev.get("startDate"),
        "venue_name": loc.get("name") or "",
        "canceled": ev.get("status") == "CANCELED",
        "at_capacity": bool(ev.get("atCapacity")),
        "is_capped": bool(ev.get("isCapped")),
        "owner_count": len([o for o in owners if o.get("id")]),
        "going_guest_count": ev.get("goingGuestCount") or ev.get("guestCount"),
        "total_guest_count": ev.get("guestCount"),
        "remaining_capacity": ev.get("remainingCapacity"),
    }


def stored_fields(fm: dict) -> dict:
    def asbool(v):
        return v is True or v == "true"
    return {
        "title": fm.get("title"),
        "start_iso": fm.get("start_iso"),
        "venue_name": fm.get("venue_name") or "",
        "canceled": asbool(fm.get("canceled")),
        "at_capacity": asbool(fm.get("at_capacity")),
        "is_capped": asbool(fm.get("is_capped")),
        "owner_count": fm.get("owner_count"),
        "going_guest_count": fm.get("going_guest_count"),
        "total_guest_count": fm.get("total_guest_count"),
        "remaining_capacity": fm.get("remaining_capacity"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--sample", type=int, default=24)
    ap.add_argument("--added-ids", help="file with one added event_id per line")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    rnd = random.Random(args.seed)
    events_dir = pathlib.Path(args.events)
    by_id = {}
    for p in events_dir.glob("*.md"):
        fm = parse_fm(p.read_text(encoding="utf-8"))
        eid = fm.get("event_id")
        if eid and fm.get("fetch_status") == "ok":
            by_id[eid] = (p, fm)

    added = set()
    if args.added_ids and pathlib.Path(args.added_ids).exists():
        added = {l.strip() for l in open(args.added_ids) if l.strip()}

    cancelled = [e for e, (_, fm) in by_id.items()
                 if fm.get("canceled") in (True, "true")]
    atcap = [e for e, (_, fm) in by_id.items()
             if fm.get("at_capacity") in (True, "true")]
    added_ok = [e for e in added if e in by_id]

    # Build a sample spanning categories, then top up with random picks.
    pick: list[str] = []
    for bucket in (added_ok, cancelled, atcap):
        rnd.shuffle(bucket)
        pick += bucket[:6]
    pool = [e for e in by_id if e not in pick]
    rnd.shuffle(pool)
    pick += pool[: max(0, args.sample - len(pick))]
    pick = list(dict.fromkeys(pick))[: args.sample]

    L = ["# Spot-check vs live Partiful\n",
         f"Sampled {len(pick)} events "
         f"(added={len([e for e in pick if e in added])}, "
         f"cancelled={len([e for e in pick if e in cancelled])}, "
         f"at-capacity={len([e for e in pick if e in atcap])}, "
         f"rest random).\n"]
    hard_fail = soft_drift = fetch_err = 0
    rows = []
    for eid in pick:
        path, fm = by_id[eid]
        url = fm.get("rsvp_url")
        try:
            ev = fetch_live(url)
        except Exception as e:
            fetch_err += 1
            rows.append(f"- ⚠ `{eid}` **{(fm.get('title') or '')[:50]}** — live fetch error: {e}")
            continue
        if not ev:
            fetch_err += 1
            rows.append(f"- ⚠ `{eid}` — no __NEXT_DATA__ on live page ({url})")
            continue
        s, live = stored_fields(fm), live_fields(ev)
        hmis = [f for f in HARD if norm(s[f]) != norm(live[f])]
        smis = [f for f in SOFT if norm(s[f]) != norm(live[f])]
        tag = "✅" if not hmis else "❌"
        if hmis:
            hard_fail += 1
        if smis:
            soft_drift += 1
        line = f"- {tag} `{eid}` **{(s['title'] or '')[:50]}**"
        if hmis:
            line += "\n    HARD MISMATCH:"
            for f in hmis:
                line += f"\n      - `{f}`: stored={s[f]!r} live={live[f]!r}"
        if smis:
            parts = ", ".join(f"{f} {s[f]}→{live[f]}" for f in smis)
            line += f"\n    soft drift: {parts}"
        rows.append(line)

    L.append(f"**Result: {len(pick)-hard_fail-fetch_err}/{len(pick)} clean, "
             f"{hard_fail} hard mismatch, {soft_drift} soft drift, "
             f"{fetch_err} fetch errors.**\n")
    L += rows
    pathlib.Path(args.out).write_text("\n".join(L), encoding="utf-8")
    print(f"[spot-check] {len(pick)} sampled: {hard_fail} hard fail, "
          f"{soft_drift} soft drift, {fetch_err} fetch err → {args.out}")
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
