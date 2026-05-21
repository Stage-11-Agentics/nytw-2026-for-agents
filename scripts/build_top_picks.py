#!/usr/bin/env python3
"""
Build TOP-PICKS.md from scored.jsonl — curated shortlist for Atin/Stage 11.

Usage:
    python3 scripts/build_top_picks.py --scored scored.jsonl --out TOP-PICKS.md
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from collections import defaultdict
from datetime import datetime


DAY_LABELS = {
    "2026-06-01": "Monday, June 1",
    "2026-06-02": "Tuesday, June 2",
    "2026-06-03": "Wednesday, June 3",
    "2026-06-04": "Thursday, June 4",
    "2026-06-05": "Friday, June 5",
    "2026-06-06": "Saturday, June 6",
    "2026-06-07": "Sunday, June 7",
}


def slot_label(start_iso: str | None) -> str:
    if not start_iso:
        return "?"
    try:
        from zoneinfo import ZoneInfo
        dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00")).astimezone(
            ZoneInfo("America/New_York")
        )
        hour = dt.hour
        if hour < 11:
            return "Morning"
        if hour < 14:
            return "Midday"
        if hour < 17:
            return "Afternoon"
        if hour < 20:
            return "Evening"
        return "Late"
    except Exception:
        return "?"


def file_link(event_id: str, all_files: dict) -> str:
    return all_files.get(event_id, "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scored", required=True)
    ap.add_argument("--events", default="events/")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.scored)]

    # Build event_id → filename map
    events_dir = pathlib.Path(args.events)
    id_to_file = {}
    for f in events_dir.glob("*.md"):
        s = f.read_text(encoding="utf-8")
        m = re.search(r'event_id:\s*"([^"]+)"', s)
        if m:
            id_to_file[m.group(1)] = f.name

    # Sort by score desc, then date asc, then start_iso asc
    rows.sort(key=lambda r: (-r["score"], r["date"] or "", r["start_iso"] or ""))

    # Tier S = top 12 by score
    tier_s = rows[:12]
    tier_s_ids = {r["event_id"] for r in tier_s}

    # Per-day picks: take top 8 per day from category in [agent_orchestration, ai_infra, talent, founders_general]
    by_day = defaultdict(list)
    for r in rows:
        if r["category"] in ("agent_orchestration", "ai_infra", "talent", "founders_general"):
            if r["score"] >= 4:
                by_day[r["date"]].append(r)
    for d in by_day:
        by_day[d].sort(key=lambda r: (r["start_iso"] or "", -r["score"]))

    out = []
    out.append("# Tech Week NYC 2026 — Top Picks for Atin")
    out.append("")
    out.append(
        "_Solo technical founder of Stage 11. Lens: **agent orchestration / "
        "autonomous companies** + **talent (high-signal engineers and operators)**. "
        "Based in Two Bridges; Manhattan-centric. Auto-generated from `scored.jsonl`._"
    )
    out.append("")
    out.append(
        "How to read this: events are scored by keyword + host + neighborhood. "
        "Higher scores mean stronger Stage 11 fit. **Tier S** = the absolute must-consider events. "
        "Then a day-by-day shortlist. Capacity warnings inline. The base dataset at `events/` "
        "is unopinionated; the picks here are Atin-specific and live separately."
    )
    out.append("")
    out.append("**Stats from scoring:**")
    from collections import Counter
    cats = Counter(r["category"] for r in rows)
    out.append(f"- {cats.get('agent_orchestration', 0)} events tagged `agent_orchestration`")
    out.append(f"- {cats.get('ai_infra', 0)} events tagged `ai_infra`")
    out.append(f"- {cats.get('talent', 0)} events tagged `talent`")
    out.append(f"- {cats.get('founders_general', 0)} events tagged `founders_general`")
    out.append(f"- {cats.get('skip', 0)} events filtered out as not-a-fit")
    out.append("")

    # Tier S
    out.append("## Tier S — must-consider")
    out.append("")
    out.append(
        "These are the 12 highest-scoring events for the Stage 11 thesis. "
        "If a week is tight, optimize around these first."
    )
    out.append("")
    for r in tier_s:
        fname = id_to_file.get(r["event_id"], "")
        link = f"[{r['title']}](events/{fname})" if fname else r["title"]
        cap = " · ⚠ **AT CAPACITY**" if r.get("at_capacity") else ""
        action = ""
        if r.get("guest_action") == "APPLY":
            action = " · _apply_"
        out.append(f"- **[s={r['score']}]** {link}")
        out.append(
            f"    - {DAY_LABELS.get(r['date'], r['date'])} · "
            f"{r['start_time'] or '?'} · "
            f"{r['neighborhood'] or '?'} · "
            f"_{r['host'] or '?'}_{cap}{action}"
        )
        out.append(f"    - [Apply / RSVP →]({r['rsvp_url']})")
    out.append("")

    # By-day
    out.append("## Day-by-day shortlist")
    out.append("")
    out.append(
        "Picks per day, sorted by start time. Stars indicate score: ★★★★★ (12+), ★★★★ (8-11), "
        "★★★ (5-7), ★★ (3-4). Where two events overlap, treat as a slot conflict — pick one."
    )
    out.append("")
    for d in sorted(by_day.keys()):
        if not d or d not in DAY_LABELS:
            continue
        events = by_day[d]
        out.append(f"### {DAY_LABELS[d]}")
        out.append("")
        # Show up to 12 per day
        for r in events[:12]:
            stars = (
                "★★★★★" if r["score"] >= 12
                else "★★★★" if r["score"] >= 8
                else "★★★" if r["score"] >= 5
                else "★★"
            )
            fname = id_to_file.get(r["event_id"], "")
            link = f"[{r['title']}](events/{fname})" if fname else r["title"]
            cap = " ⚠cap" if r.get("at_capacity") else ""
            tier = " 🌟 Tier S" if r["event_id"] in tier_s_ids else ""
            out.append(
                f"- `{r['start_time'] or '':>9}` {stars} {link}{tier}{cap}"
            )
            out.append(
                f"    - {r['neighborhood'] or '?':15} · _{r['host'] or '?'}_ · "
                f"[{r['category']}] · [RSVP →]({r['rsvp_url']})"
            )
        out.append("")

    # Notes
    out.append("## How the scoring works")
    out.append("")
    out.append(
        "See `scripts/score.py` for the full keyword/host/geography weights. "
        "Short version:"
    )
    out.append("")
    out.append("- **Agent keywords** (cap +20): `agent`, `agentic`, `multi-agent`, `MCP`, `autonomous`, "
               "`agent orchestration`, `browser use`, `voice agent`, etc.")
    out.append("- **Talent keywords** (cap +10): `betaworks`, `south park commons`, `cursor`, `replit`, "
               "`vercel`, `a16z speedrun`, `hackathon`, `head of (eng|ai|infra)`, etc.")
    out.append("- **Negatives** (floor -8): `crypto`, `web3`, `nft`, `fashion`, `wellness`, "
               "`yoga`, `golf`, `students only`, `legal`, etc.")
    out.append("- **Geography**: +2 for Chinatown/LES/FiDi (Two Bridges adjacent), 0 for Midtown, "
               "-1 for Brooklyn/UES/UWS, -2 for LIC/Queens/Harlem, -3 for virtual.")
    out.append("- **Host bonus** (cap +6): Stage-11-adjacent hosts get +1 to +4 depending on "
               "alignment (Anthropic, Browserbase, South Park Commons highest).")
    out.append("")
    out.append("To recompute: `python3 scripts/score.py --events events/ --out scored.jsonl && "
               "python3 scripts/build_top_picks.py --scored scored.jsonl --out TOP-PICKS.md`")
    out.append("")

    pathlib.Path(args.out).write_text("\n".join(out), encoding="utf-8")
    print(f"[picks] wrote {args.out}")
    print(f"  Tier S: {len(tier_s)} events")
    print(f"  Day-by-day: {sum(min(12,len(v)) for v in by_day.values())} events listed")


if __name__ == "__main__":
    main()
