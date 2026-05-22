#!/usr/bin/env python3
"""
Re-render the body of each event markdown file from frontmatter data:
- Inline image at top
- Capacity line (when isCapped)
- Hosts line that surfaces owner_count when > 1 calendar host
- Existing description preserved verbatim

Idempotent — re-runnable. Detects "between the H1 and the ## Description" as the
header block to regenerate.

Usage:
    python3 scripts/render_body.py --events events/
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re


FRONTMATTER_RE = re.compile(r"^(---\n)(.+?)(\n---\n)(.*)", re.S)

# Partiful platform admin auto-added to most NYTW events.
PLATFORM_ADMIN_ID = "7DFu4rITofNzKIjA7hCx"


def parse_fm(block: str) -> dict:
    fm = {}
    for line in block.split("\n"):
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
        else:
            try:
                v = int(v)
            except ValueError:
                pass
        fm[k] = v
    return fm


def render_resolved_hosts_block(fm: dict, users: dict) -> str:
    """Produce a markdown block listing each resolved host on Partiful."""
    owner_ids = fm.get("owner_ids") or []
    if not owner_ids:
        return ""
    lines = []
    real_hosts = [oid for oid in owner_ids if oid != PLATFORM_ADMIN_ID]
    has_admin = PLATFORM_ADMIN_ID in owner_ids
    if not real_hosts:
        return ""
    lines.append("### Hosts on Partiful")
    lines.append("")
    for oid in real_hosts:
        u = users.get(oid)
        if not u:
            lines.append(f"- [user `{oid}`](https://partiful.com/u/{oid}) _(name not resolved)_")
            continue
        name = (u.get("name") or "").strip() or f"`{oid}`"
        bio = (u.get("bio") or "").strip()
        line = f"- [{name}](https://partiful.com/u/{oid})"
        if bio:
            line += f" — _{bio}_"
        lines.append(line)
    if has_admin:
        lines.append(
            f"- _(plus Partiful platform admin `{PLATFORM_ADMIN_ID}` — auto-added to most events)_"
        )
    lines.append("")
    return "\n".join(lines)


def render_header(fm: dict) -> str:
    title = fm.get("title", "")
    host = fm.get("host", "") or ""
    owner_count = fm.get("owner_count")
    when_parts = []
    if fm.get("day"):
        when_parts.append(fm["day"])
    if fm.get("date"):
        when_parts.append(fm["date"])
    when_str = ""
    if fm.get("start_iso") and fm.get("day"):
        # Pretty date: "Tuesday, June 2, 2026"
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            dt = datetime.fromisoformat(fm["start_iso"].replace("Z", "+00:00")).astimezone(
                ZoneInfo("America/New_York")
            )
            day_label = dt.strftime("%A, %B %-d, %Y")
        except Exception:
            day_label = f"{fm['day']}, {fm.get('date', '')}"
        # start_time / end_time already include " ET"
        start = (fm.get("start_time", "") or "").replace(" ET", "")
        end = (fm.get("end_time", "") or "").replace(" ET", "")
        when_str = f"{day_label} · {start}"
        if end:
            when_str += f"–{end}"
        when_str += " ET"
    elif fm.get("day") and fm.get("start_time"):
        when_str = f"{fm['day']}, {fm.get('date','')} · {fm.get('start_time','')}"
        if fm.get("end_time"):
            when_str += f"–{fm['end_time']}"

    where_parts = []
    if fm.get("venue_name"):
        where_parts.append(fm["venue_name"])
    if fm.get("venue_address"):
        where_parts.append(fm["venue_address"])
    if fm.get("neighborhood"):
        where_parts.append(fm["neighborhood"])
    where_str = " · ".join(where_parts)

    rsvp_url = fm.get("rsvp_url", "")
    google_maps = fm.get("google_maps", "")
    local_image = fm.get("local_image", "")
    image_remote = fm.get("image", "")

    is_capped = fm.get("is_capped")
    max_cap = fm.get("max_capacity")
    rem_cap = fm.get("remaining_capacity")
    going = fm.get("going_guest_count") or fm.get("approved_guest_count")
    total_count = fm.get("total_guest_count")

    visibility = fm.get("visibility", "")
    at_capacity = fm.get("at_capacity")
    guest_action = fm.get("guest_action", "")

    canceled = fm.get("canceled") is True or fm.get("canceled") == "true"
    canceled_at = fm.get("canceled_at", "")
    cancellation_message = fm.get("cancellation_message", "")

    lines = []
    lines.append(f"# {title}")
    lines.append("")
    if canceled:
        banner = "> ## ⚠ CANCELED"
        if canceled_at:
            banner += f"  \n> _canceled {canceled_at}_"
        if cancellation_message:
            msg = cancellation_message.replace("\n", "  \n> ")
            banner += f"  \n>  \n> {msg}"
        lines.append(banner)
        lines.append("")
    # Image
    if local_image:
        lines.append(f"![{title}]({local_image})")
        lines.append("")
    elif image_remote:
        lines.append(f"![{title}]({image_remote})")
        lines.append("")
    # Host(s)
    if host:
        if isinstance(owner_count, int) and owner_count > 0:
            # Calendar shows N hosts joined by commas; owner_count is Partiful's authoritative count.
            calendar_hosts = [h.strip() for h in host.split(",") if h.strip()]
            if owner_count > len(calendar_hosts):
                lines.append(
                    f"**Hosts:** {host}  _(+{owner_count - len(calendar_hosts)} more host(s) "
                    f"on Partiful — see description for full list)_"
                )
            else:
                lines.append(f"**Hosts:** {host}")
        else:
            lines.append(f"**Hosts:** {host}")
    # When
    if when_str:
        lines.append(f"**When:** {when_str}")
    # Where
    if where_str:
        lines.append(f"**Where:** {where_str}")
    # Capacity
    if is_capped and isinstance(max_cap, int):
        cap_line = f"**Capacity:** capped at {max_cap}"
        if isinstance(rem_cap, int):
            taken = max_cap - rem_cap
            cap_line += f" · {taken} taken, {rem_cap} remaining"
            if rem_cap == 0:
                cap_line += " · ⚠ **FULL**"
        lines.append(cap_line)
    elif isinstance(going, int) and going > 0:
        lines.append(f"**Going:** {going}" + (f" of {total_count}" if total_count and total_count != going else ""))
    if at_capacity:
        lines.append("**Status:** ⚠ at capacity")
    if guest_action == "APPLY":
        lines.append("**Access:** apply / hosts approve")
    if visibility and visibility != "public":
        lines.append(f"**Visibility:** {visibility}")
    # RSVP / Map
    if rsvp_url:
        lines.append(f"**RSVP:** {rsvp_url}")
    if google_maps:
        lines.append(f"**Map:** {google_maps}")
    return "\n".join(lines)


def render_footer(fm: dict) -> str:
    rsvp_url = fm.get("rsvp_url", "")
    action = "Apply" if fm.get("guest_action") == "APPLY" else "RSVP"
    return f"---\n\n[{action} on Partiful →]({rsvp_url})\n"


def process_one(path: pathlib.Path, users: dict) -> str:
    content = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(content)
    if not m:
        return "no_frontmatter"
    fm = parse_fm(m.group(2))
    body = m.group(4)

    # Find description marker
    desc_match = re.search(r"\n## Description\n", body)
    if not desc_match:
        if "fetch_status: failed" in m.group(2):
            return "stub_skipped"
        return "no_description_marker"

    desc_start = desc_match.start()
    footer_match = re.search(r"\n---\n\n\[(?:Apply|RSVP)", body[desc_start:])
    if footer_match:
        desc_end = desc_start + footer_match.start()
    else:
        desc_end = len(body)
    description_section = body[desc_start:desc_end]

    header = render_header(fm)
    resolved_block = render_resolved_hosts_block(fm, users)
    footer = render_footer(fm)

    parts = [header]
    if resolved_block:
        parts.append("")
        parts.append(resolved_block)
    parts.append(description_section)
    new_body = "\n" + "\n".join(parts) + "\n\n" + footer
    new_content = m.group(1) + m.group(2) + m.group(3) + new_body

    if new_content != content:
        path.write_text(new_content, encoding="utf-8")
        return "rendered"
    return "unchanged"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--users", default="users.json")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    users = {}
    users_path = pathlib.Path(args.users)
    if users_path.exists():
        try:
            users = json.load(open(users_path))
            print(f"[render] loaded {len(users)} resolved users from {args.users}")
        except json.JSONDecodeError:
            print(f"[render] could not parse {args.users}, skipping host resolution")

    events_dir = pathlib.Path(args.events)
    files = sorted(events_dir.glob("*.md"))
    if args.limit:
        files = files[: args.limit]

    counts = {}
    for f in files:
        s = process_one(f, users)
        counts[s] = counts.get(s, 0) + 1

    print(f"[render] processed {len(files)} files: {counts}")


if __name__ == "__main__":
    main()
