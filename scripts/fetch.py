#!/usr/bin/env python3
"""
Fetch every Partiful event referenced in manifest.json and write one
markdown file per event under events/.

Usage:
    python3 scripts/fetch.py --manifest manifest.json --out events/
    python3 scripts/fetch.py --manifest manifest.json --out events/ --concurrency 8
    python3 scripts/fetch.py --manifest manifest.json --out events/ --resume
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import pathlib
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)

NEXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>', re.S
)


def slugify(text: str, maxlen: int = 80) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    s = re.sub(r"-+", "-", s)
    return s[:maxlen].rstrip("-") or "event"


def fmt_time(dt: datetime) -> str:
    h = dt.strftime("%I").lstrip("0") or "12"
    m = dt.strftime("%M")
    ap = dt.strftime("%p").lower()
    return f"{h}:{m}{ap}"


def fetch(url: str, timeout: float = 25.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        # Best-effort decoding
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            return body.decode("utf-8", errors="replace")


def parse_partiful(html: str) -> dict | None:
    m = NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return data.get("props", {}).get("pageProps", {}).get("event")


def yaml_escape(s: str | None) -> str:
    if s is None:
        return '""'
    s = str(s)
    if '"' in s or "\\" in s or ":" in s or "\n" in s:
        return json.dumps(s, ensure_ascii=False)
    return f'"{s}"'


def render_markdown(manifest_row: dict, partiful: dict | None) -> tuple[str, str]:
    """Return (filename_without_dir, content)."""
    url = manifest_row["url"]
    event_id = url.rstrip("/").split("/")[-1]
    badges = manifest_row.get("badges", []) or []
    calendar_host = manifest_row.get("host", "")
    calendar_neighborhood = manifest_row.get("neighborhood", "")
    calendar_dateTime = manifest_row.get("dateTime", "")
    calendar_title = manifest_row.get("title", "")

    if partiful is None:
        # Couldn't fetch / parse. Make a stub from manifest data only.
        slug = slugify(calendar_title or event_id)
        fname = f"unknown-date-{slug}-{event_id}.md"
        body_lines = [
            "---",
            f"title: {yaml_escape(calendar_title)}",
            f"event_id: {yaml_escape(event_id)}",
            f"rsvp_url: {yaml_escape(url)}",
            f"host: {yaml_escape(calendar_host)}",
            f"neighborhood: {yaml_escape(calendar_neighborhood)}",
            f"calendar_datetime: {yaml_escape(calendar_dateTime)}",
            f"badges: {json.dumps(badges)}",
            "fetch_status: failed",
            "---",
            "",
            f"# {calendar_title}",
            "",
            f"**Host:** {calendar_host}",
            f"**When:** {calendar_dateTime}",
            f"**Where:** {calendar_neighborhood}",
            f"**RSVP:** {url}",
            "",
            "## Description",
            "",
            "_Could not fetch Partiful page at crawl time. Click the RSVP link for full details._",
            "",
            f"[RSVP / Apply →]({url})",
            "",
        ]
        return fname, "\n".join(body_lines)

    # Title (Partiful sometimes includes "#NYTechWeek" suffix — keep but allow display variant)
    p_title = (partiful.get("title") or calendar_title or "").strip()
    display_title = re.sub(r"\s*-?\s*#NYTechWeek\s*$", "", p_title).strip()

    # Dates → ET
    start_iso = partiful.get("startDate")
    end_iso = partiful.get("endDate")
    start_dt = (
        datetime.fromisoformat(start_iso.replace("Z", "+00:00")).astimezone(ET)
        if start_iso
        else None
    )
    end_dt = (
        datetime.fromisoformat(end_iso.replace("Z", "+00:00")).astimezone(ET)
        if end_iso
        else None
    )

    date_str = start_dt.strftime("%Y-%m-%d") if start_dt else "unknown-date"
    day_str = start_dt.strftime("%A") if start_dt else ""
    start_time_str = fmt_time(start_dt) if start_dt else ""
    end_time_str = fmt_time(end_dt) if end_dt else ""
    when_str = (
        f"{day_str}, {start_dt.strftime('%B %-d, %Y')} · {start_time_str}"
        + (f"–{end_time_str}" if end_dt else "")
        + " ET"
        if start_dt
        else calendar_dateTime
    )
    file_time = start_dt.strftime("%H%M") if start_dt else "0000"

    # Location
    loc = partiful.get("locationInfo") or {}
    maps = loc.get("mapsInfo") or {}
    venue_name = maps.get("name") or ""
    address_lines = maps.get("addressLines") or loc.get("displayAddressLines") or []
    venue_address = ", ".join(a for a in address_lines if a)
    google_maps = maps.get("googleMapsUrl") or ""

    # Image
    image = partiful.get("image") or {}
    image_url = image.get("url") or ""

    # Misc
    public_short = partiful.get("publicShortUrl") or ""
    visibility = partiful.get("visibility") or ""
    guest_action = partiful.get("guestAction") or ""
    at_capacity = bool(partiful.get("atCapacity"))
    guest_count = partiful.get("goingGuestCount") or partiful.get("guestCount") or 0
    description = (partiful.get("description") or "").strip()

    slug = slugify(display_title) or event_id
    fname = f"{date_str}-{file_time}-{slug}.md"

    fm_lines = ["---"]
    fm_lines.append(f"title: {yaml_escape(display_title)}")
    fm_lines.append(f"event_id: {yaml_escape(event_id)}")
    fm_lines.append(f"date: {date_str}")
    if day_str:
        fm_lines.append(f"day: {yaml_escape(day_str)}")
    if start_time_str:
        fm_lines.append(f"start_time: {yaml_escape(start_time_str + ' ET')}")
    if end_time_str:
        fm_lines.append(f"end_time: {yaml_escape(end_time_str + ' ET')}")
    if start_iso:
        fm_lines.append(f"start_iso: {yaml_escape(start_iso)}")
    if end_iso:
        fm_lines.append(f"end_iso: {yaml_escape(end_iso)}")
    fm_lines.append(f"host: {yaml_escape(calendar_host)}")
    if venue_name:
        fm_lines.append(f"venue_name: {yaml_escape(venue_name)}")
    if venue_address:
        fm_lines.append(f"venue_address: {yaml_escape(venue_address)}")
    fm_lines.append(f"neighborhood: {yaml_escape(calendar_neighborhood)}")
    fm_lines.append(f"rsvp_url: {yaml_escape(url)}")
    if public_short:
        fm_lines.append(f"public_short_url: {yaml_escape(public_short)}")
    if google_maps:
        fm_lines.append(f"google_maps: {yaml_escape(google_maps)}")
    if image_url:
        fm_lines.append(f"image: {yaml_escape(image_url)}")
    if visibility:
        fm_lines.append(f"visibility: {yaml_escape(visibility)}")
    if guest_action:
        fm_lines.append(f"guest_action: {yaml_escape(guest_action)}")
    fm_lines.append(f"at_capacity: {'true' if at_capacity else 'false'}")
    if guest_count:
        fm_lines.append(f"going_guest_count: {guest_count}")
    fm_lines.append(f"badges: {json.dumps(badges)}")
    fm_lines.append("fetch_status: ok")
    fm_lines.append("---")

    body_lines = [
        "",
        f"# {display_title}",
        "",
    ]
    body_lines.append(f"**Host:** {calendar_host}" if calendar_host else "")
    body_lines.append(f"**When:** {when_str}" if when_str else "")
    where_parts = [p for p in [venue_name, venue_address, calendar_neighborhood] if p]
    if where_parts:
        body_lines.append(f"**Where:** {' · '.join(where_parts)}")
    body_lines.append(f"**RSVP:** {url}")
    if google_maps:
        body_lines.append(f"**Map:** {google_maps}")
    body_lines.append("")
    body_lines.append("## Description")
    body_lines.append("")
    body_lines.append(description or "_(No description provided.)_")
    body_lines.append("")
    body_lines.append("---")
    body_lines.append("")
    action_label = "Apply" if guest_action == "APPLY" else "RSVP"
    body_lines.append(f"[{action_label} on Partiful →]({url})")
    body_lines.append("")

    content = "\n".join(fm_lines + [l for l in body_lines if l is not None])
    return fname, content


def process_one(row: dict, out_dir: pathlib.Path, resume: bool, retry: int = 2) -> dict:
    url = row["url"]
    event_id = url.rstrip("/").split("/")[-1]
    # Skip if any file already exists for this event_id (resume mode)
    if resume:
        existing = list(out_dir.glob(f"*{event_id}*.md"))
        if existing:
            return {"event_id": event_id, "status": "skipped", "file": existing[0].name}

    last_err = None
    for attempt in range(retry + 1):
        try:
            html = fetch(url)
            partiful = parse_partiful(html)
            fname, content = render_markdown(row, partiful)
            (out_dir / fname).write_text(content, encoding="utf-8")
            return {
                "event_id": event_id,
                "status": "ok" if partiful else "stub",
                "file": fname,
            }
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = str(e)
            if attempt < retry:
                time.sleep(1.5 * (attempt + 1))
                continue
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            break

    # Total failure: still emit a stub from manifest data
    fname, content = render_markdown(row, None)
    (out_dir / fname).write_text(content, encoding="utf-8")
    return {"event_id": event_id, "status": "failed", "file": fname, "error": last_err}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of events (debug)")
    args = ap.parse_args()

    manifest = json.load(open(args.manifest))
    events = manifest["events"]
    if args.limit:
        events = events[: args.limit]

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    total = len(events)
    print(f"[fetch] processing {total} events with concurrency={args.concurrency}", flush=True)

    results = {"ok": 0, "stub": 0, "failed": 0, "skipped": 0}
    log_path = out_dir.parent / "fetch.log"
    with open(log_path, "a") as logf:
        logf.write(f"\n=== run start {datetime.now().isoformat()} total={total} ===\n")
        with cf.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {pool.submit(process_one, row, out_dir, args.resume): row for row in events}
            done_count = 0
            for fut in cf.as_completed(futures):
                r = fut.result()
                results[r["status"]] = results.get(r["status"], 0) + 1
                done_count += 1
                if done_count % 50 == 0 or done_count == total:
                    print(
                        f"  [{done_count}/{total}] ok={results['ok']} "
                        f"stub={results['stub']} failed={results['failed']} "
                        f"skipped={results['skipped']}",
                        flush=True,
                    )
                logf.write(json.dumps(r) + "\n")
        logf.write(f"=== run done {datetime.now().isoformat()} {results} ===\n")

    print(f"[fetch] done: {results}")


if __name__ == "__main__":
    main()
