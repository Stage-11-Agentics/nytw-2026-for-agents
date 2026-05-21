#!/usr/bin/env python3
"""
Patch host / neighborhood / badges into existing event markdown files
from a refreshed manifest.json. Also re-renders the body's Host: / Where: lines.

Does NOT re-fetch Partiful — uses what's already in each file.

Usage:
    python3 scripts/patch_metadata.py --manifest manifest.json --events events/
    python3 scripts/patch_metadata.py --manifest manifest.json --events events/ --limit 40
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


FRONTMATTER_RE = re.compile(r"^(---\n)(.+?)(\n---\n)", re.S)


def yaml_escape(s):
    if s is None:
        return '""'
    s = str(s)
    if '"' in s or "\\" in s or ":" in s or "\n" in s:
        return json.dumps(s, ensure_ascii=False)
    return f'"{s}"'


def patch_frontmatter_block(block: str, host: str, neighborhood: str, badges: list) -> str:
    """Replace host/neighborhood/badges lines in a frontmatter YAML block."""
    lines = block.split("\n")
    new_lines = []
    seen = set()
    for line in lines:
        if line.startswith("host:"):
            new_lines.append(f"host: {yaml_escape(host)}")
            seen.add("host")
        elif line.startswith("neighborhood:"):
            new_lines.append(f"neighborhood: {yaml_escape(neighborhood)}")
            seen.add("neighborhood")
        elif line.startswith("badges:"):
            new_lines.append(f"badges: {json.dumps(badges)}")
            seen.add("badges")
        else:
            new_lines.append(line)
    # Insert any missing fields just before the closing
    if "host" not in seen:
        new_lines.append(f"host: {yaml_escape(host)}")
    if "neighborhood" not in seen:
        new_lines.append(f"neighborhood: {yaml_escape(neighborhood)}")
    if "badges" not in seen:
        new_lines.append(f"badges: {json.dumps(badges)}")
    return "\n".join(new_lines)


def patch_body(body: str, host: str, neighborhood: str) -> str:
    """Patch Host: and Where: lines (or insert them)."""
    has_host_line = re.search(r"^\*\*Host:\*\*", body, re.M)
    has_where_line = re.search(r"^\*\*Where:\*\*", body, re.M)

    if host:
        if has_host_line:
            body = re.sub(
                r"^\*\*Host:\*\*.*$",
                f"**Host:** {host}",
                body,
                count=1,
                flags=re.M,
            )
        else:
            # Insert after the title H1
            body = re.sub(
                r"^(# .+?\n)(\n?)",
                lambda m: f"{m.group(1)}\n**Host:** {host}\n",
                body,
                count=1,
                flags=re.M,
            )

    if neighborhood:
        # If Where: exists, append neighborhood if missing; otherwise insert one.
        if has_where_line:
            body = re.sub(
                r"^(\*\*Where:\*\* .*)$",
                lambda m: (
                    m.group(1)
                    if neighborhood in m.group(1)
                    else f"{m.group(1)} · {neighborhood}"
                ),
                body,
                count=1,
                flags=re.M,
            )
        else:
            # Insert after **When:** if present, else after Host
            anchor = r"^(\*\*When:\*\*.*)$"
            if re.search(anchor, body, re.M):
                body = re.sub(
                    anchor,
                    lambda m: f"{m.group(1)}\n**Where:** {neighborhood}",
                    body,
                    count=1,
                    flags=re.M,
                )

    return body


def event_id_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    manifest = json.load(open(args.manifest))
    events = manifest["events"]
    events_dir = pathlib.Path(args.events)

    # Build event_id → file map
    id_to_file = {}
    for f in events_dir.glob("*.md"):
        s = f.read_text(encoding="utf-8")
        m = re.search(r'event_id:\s*"([^"]+)"', s)
        if m:
            id_to_file[m.group(1)] = f

    processed = 0
    patched = 0
    missing = 0
    for ev in events:
        if args.limit and processed >= args.limit:
            break
        ev_id = event_id_from_url(ev["url"])
        f = id_to_file.get(ev_id)
        if not f:
            missing += 1
            processed += 1
            continue
        content = f.read_text(encoding="utf-8")
        m = FRONTMATTER_RE.match(content)
        if not m:
            processed += 1
            continue
        new_block = patch_frontmatter_block(
            m.group(2),
            ev.get("host", ""),
            ev.get("neighborhood", ""),
            ev.get("badges", []) or [],
        )
        new_body = patch_body(
            content[m.end():],
            ev.get("host", ""),
            ev.get("neighborhood", ""),
        )
        new_content = m.group(1) + new_block + m.group(3) + new_body
        if new_content != content:
            patched += 1
            if not args.dry_run:
                f.write_text(new_content, encoding="utf-8")
        processed += 1

    print(
        f"[patch] processed={processed} patched={patched} "
        f"missing_files={missing}"
    )


if __name__ == "__main__":
    main()
