#!/usr/bin/env python3
"""
Crawl every event listed on https://www.tech-week.com/calendar/nyc and emit
manifest.json. Uses a two-pass scroll-and-revisit strategy to avoid the
virtualization race condition documented in
https://github.com/Stage-11-Agentics/nytw-2026-for-agents/issues/1.

Why two passes:
  tech-week.com renders the event table with virtualized rows — only ~50 rows
  live in the DOM at any moment. A naive scroll-and-snapshot loop can miss
  rows that mount and unmount within a single scroll tick. The fix is to
  scroll the table twice (top-to-bottom, then top-to-bottom again), dedupe
  captures by event ID, and assert the final count against the page's own
  matching-events counter.

Usage:
    python3 scripts/crawl_manifest.py --out manifest.json
    python3 scripts/crawl_manifest.py --out manifest.json --include-invite-only
    python3 scripts/crawl_manifest.py --out manifest.json --headed   # debug
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    sys.exit(
        "playwright is required.\n"
        "  pip install playwright\n"
        "  python3 -m playwright install chromium"
    )


CALENDAR_URL = "https://www.tech-week.com/calendar/nyc"

# Scroll step as a fraction of viewport height. Smaller = each row visible for
# more ticks = fewer race-condition misses. 0.6 is the sweet spot.
SCROLL_STEP = 0.6

# Tick delay (seconds) between scroll and extract. Lets React commit before we
# read DOM. 0.30s is generous; tune down if you can verify React settle time.
SCROLL_DELAY = 0.30

# Consecutive ticks with no new events before a pass declares itself done.
STABLE_TICKS_TO_FINISH = 12

# Hard cap on scroll ticks per pass. 1,598 events / ~10 per viewport ≈ 160 ticks
# of headroom; 500 is far more than necessary.
MAX_TICKS_PER_PASS = 500


# JS that extracts the current set of rendered table rows, returning the React
# row.original objects. tech-week.com uses @tanstack/react-table v8, which
# exposes row.original on each tr via __reactProps$<hash>.row.
EXTRACT_JS = r"""
() => {
  const rows = document.querySelectorAll('tbody tr');
  const out = [];
  for (const tr of rows) {
    const key = Object.keys(tr).find(k => k.startsWith('__reactFiber'));
    if (!key) continue;
    let f = tr[key];
    let depth = 0;
    while (f && depth < 6) {
      const p = f.memoizedProps || {};
      const orig = p.row && p.row.original;
      if (orig && orig.id != null) {
        const hosts = (orig.facets && orig.facets.hosts)
          ? orig.facets.hosts.map(h => h.label)
          : [];
        out.push({
          id: orig.id,
          name: orig.name,
          date: orig.date,
          time: orig.time,
          location: orig.location,
          company: orig.company,
          externalHref: orig.externalHref,
          isInviteOnly: !!orig.isInviteOnly,
          hosts,
        });
        break;
      }
      f = f.return;
      depth++;
    }
  }
  return out;
}
"""


# JS to read the "N matching events" counter the page renders. Returns null if
# the counter is not present (e.g. layout change).
COUNTER_JS = r"""
() => {
  const m = (document.body.innerText || '').match(/(\d+)\s+matching events/);
  return m ? parseInt(m[1], 10) : null;
}
"""


def scroll_pass(page, all_events: dict, pass_label: str) -> int:
    """
    One top-to-bottom scroll pass. Extracts on each tick, deduping into
    all_events by event ID. Returns the number of NEW events added in this
    pass.
    """
    page.evaluate("() => window.scrollTo(0, 0)")
    time.sleep(SCROLL_DELAY)

    starting_size = len(all_events)
    stable = 0
    last_size = -1

    for tick in range(MAX_TICKS_PER_PASS):
        for ev in page.evaluate(EXTRACT_JS):
            if ev["id"] not in all_events:
                all_events[ev["id"]] = ev

        page.evaluate(
            "(step) => window.scrollBy(0, window.innerHeight * step)",
            SCROLL_STEP,
        )
        time.sleep(SCROLL_DELAY)

        at_bottom = page.evaluate(
            "() => window.scrollY + window.innerHeight"
            " >= document.documentElement.scrollHeight - 5"
        )

        if len(all_events) == last_size:
            stable += 1
        else:
            stable = 0
        last_size = len(all_events)

        if at_bottom and stable >= STABLE_TICKS_TO_FINISH:
            break

        if tick % 20 == 0:
            print(
                f"  [{pass_label}] tick={tick:3d}  captured={len(all_events):5d}"
                f"  stable={stable:2d}  atBottom={at_bottom}"
            )

    new_added = len(all_events) - starting_size
    print(
        f"  [{pass_label}] done: ticks={tick}, total={len(all_events)},"
        f" new this pass={new_added}"
    )
    return new_added


def datetime_str(date_iso: str, time_iso: str) -> str:
    """Render the human-readable string used by the legacy manifest format."""
    d = datetime.strptime(date_iso, "%Y-%m-%d")
    hh, mm = time_iso.split(":")[:2]
    h = int(hh)
    ampm = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    mm_part = f":{mm}" if mm != "00" else ""
    return f"{d.strftime('%A')} · {d.strftime('%B')} {d.day} · {h12}{mm_part}{ampm}"


def to_manifest_entry(ev: dict) -> dict:
    hosts = ev.get("hosts") or []
    return {
        "badges": [],
        "dateTime": datetime_str(ev["date"], ev["time"]),
        "host": ev.get("company") or (hosts[0] if hosts else ""),
        "neighborhood": ev.get("location") or "",
        "source": "crawl",
        "title": ev["name"],
        "url": ev["externalHref"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out", default="manifest.json", help="Output manifest path"
    )
    ap.add_argument(
        "--include-invite-only",
        action="store_true",
        help="Include invite-only events. Default: exclude (matches existing manifest convention).",
    )
    ap.add_argument(
        "--headed",
        action="store_true",
        help="Launch a visible browser window for debugging.",
    )
    ap.add_argument(
        "--save-raw",
        help="Optional path to dump the full crawled event list (JSON), pre-filter.",
    )
    args = ap.parse_args()

    print(f"[crawl] target: {CALENDAR_URL}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        ctx = browser.new_context(viewport={"width": 1400, "height": 1600})
        page = ctx.new_page()
        page.goto(CALENDAR_URL, wait_until="networkidle", timeout=60000)

        try:
            page.wait_for_selector("tbody tr", timeout=20000)
        except PWTimeout:
            sys.exit("[crawl] timed out waiting for events table")

        expected = page.evaluate(COUNTER_JS)
        if expected is not None:
            print(f"[crawl] page reports {expected} matching events")
        else:
            print("[crawl] no 'N matching events' counter found on page")

        all_events: dict = {}
        scroll_pass(page, all_events, "pass-1")
        # Two-pass guarantee: rerun even if pass 1 felt stable. This catches the
        # virtualization race documented in issue #1.
        scroll_pass(page, all_events, "pass-2")

        # Sanity check: total captured should match the page counter within 1%.
        if expected and len(all_events) < int(expected * 0.99):
            print(
                f"\n[crawl] WARNING: captured {len(all_events)} but page claims"
                f" {expected} ({len(all_events) - expected:+d}). Running pass-3.",
                file=sys.stderr,
            )
            scroll_pass(page, all_events, "pass-3")

        browser.close()

    events = list(all_events.values())
    print(f"\n[crawl] captured {len(events)} total events")
    print(f"  invite-only: {sum(1 for e in events if e['isInviteOnly'])}")
    print(f"  public:      {sum(1 for e in events if not e['isInviteOnly'])}")

    if args.save_raw:
        with open(args.save_raw, "w") as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        print(f"[crawl] raw dump → {args.save_raw}")

    keep = events if args.include_invite_only else [
        e for e in events if not e["isInviteOnly"]
    ]
    entries = [to_manifest_entry(e) for e in keep]
    # Stable order by (date, time, id) so re-crawls produce minimal diffs.
    entries_sorted = sorted(
        keep, key=lambda e: (e["date"], e["time"], e["id"])
    )
    manifest = {
        "count": len(entries_sorted),
        "events": [to_manifest_entry(e) for e in entries_sorted],
    }
    with open(args.out, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"[crawl] wrote {len(manifest['events'])} events → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
