#!/usr/bin/env python3
"""
Enrich existing event markdown files with:
- owner_count + owner_ids (from Partiful __NEXT_DATA__)
- max_capacity + remaining_capacity + is_capped (when host caps the event)
- image saved locally to images/<event_id>.<ext>

Does NOT replace existing fields (host, title, description, etc).
Idempotent — re-runnable.

Usage:
    python3 scripts/enrich.py --events events/ --images-dir images/
    python3 scripts/enrich.py --events events/ --images-dir images/ --limit 5  # debug
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import mimetypes
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)

NEXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>', re.S
)
FRONTMATTER_RE = re.compile(r"^(---\n)(.+?)(\n---\n)(.*)", re.S)


def fetch(url: str, timeout: float = 25.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_partiful(html: str) -> dict | None:
    m = NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))["props"]["pageProps"]["event"]
    except (json.JSONDecodeError, KeyError):
        return None


def ext_for(content_type: str, url: str) -> str:
    # Prefer content-type
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            return ext.lstrip(".")
    # Fallback: parse from URL
    parsed = urllib.parse.urlparse(url)
    base = pathlib.Path(parsed.path).suffix
    if base:
        return base.lstrip(".")
    return "img"


def download_image(url: str, dest_dir: pathlib.Path, event_id: str) -> tuple[str | None, str | None]:
    """Returns (filename, content_type) or (None, error_str)."""
    # If any file with this event_id stem exists, skip
    existing = list(dest_dir.glob(f"{event_id}.*"))
    if existing:
        return existing[0].name, None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            content_type = r.headers.get("Content-Type", "")
            body = r.read()
        ext = ext_for(content_type, url)
        fname = f"{event_id}.{ext}"
        (dest_dir / fname).write_bytes(body)
        return fname, content_type
    except (urllib.error.URLError, TimeoutError) as e:
        return None, str(e)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def patch_frontmatter(block: str, updates: dict) -> str:
    """Add or replace keys in the frontmatter YAML block."""
    lines = block.split("\n")
    keys_seen = set()
    new_lines = []
    for line in lines:
        replaced = False
        for k in list(updates.keys()):
            if line.startswith(f"{k}:"):
                new_lines.append(f"{k}: {updates[k]}")
                keys_seen.add(k)
                replaced = True
                break
        if not replaced:
            new_lines.append(line)
    # Append keys not seen
    for k, v in updates.items():
        if k not in keys_seen:
            new_lines.append(f"{k}: {v}")
    return "\n".join(new_lines)


def yaml_val(v) -> str:
    if v is None:
        return '""'
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    s = str(v)
    if any(c in s for c in '":\\\n') or s.startswith("[") or s.startswith("{"):
        return json.dumps(s, ensure_ascii=False)
    return f'"{s}"'


def process_one(path: pathlib.Path, images_dir: pathlib.Path) -> dict:
    content = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(content)
    if not m:
        return {"file": path.name, "status": "no_frontmatter"}

    fm_block = m.group(2)
    body = m.group(4)

    # Extract event_id and rsvp_url
    eid_m = re.search(r'event_id:\s*"([^"]+)"', fm_block)
    url_m = re.search(r'rsvp_url:\s*"([^"]+)"', fm_block)
    fetch_ok = "fetch_status: ok" in fm_block

    if not eid_m or not url_m:
        return {"file": path.name, "status": "no_ids"}

    event_id = eid_m.group(1)
    rsvp_url = url_m.group(1)

    if not fetch_ok:
        # Stub file — nothing more we can enrich
        return {"file": path.name, "status": "stub_skipped"}

    # Re-fetch Partiful
    try:
        html = fetch(rsvp_url).decode("utf-8", errors="replace")
    except Exception as e:
        return {"file": path.name, "status": "fetch_failed", "error": str(e)}

    ev = parse_partiful(html)
    if not ev:
        return {"file": path.name, "status": "parse_failed"}

    updates = {}

    # Owner data — full list as Partiful tracks it (matches what shows on the partiful.com page).
    # 7DFu4rITofNzKIjA7hCx appears in 1,362 of ~1,374 events — likely a Partiful/TechWeek platform
    # admin auto-added across events. Stored alongside the real hosts so downstream agents can
    # filter if they want.
    owners = ev.get("owners") or []
    owner_ids = [o.get("id") for o in owners if o.get("id")]
    updates["owner_count"] = len(owner_ids)
    updates["owner_ids"] = json.dumps(owner_ids)

    # Capacity
    is_capped = bool(ev.get("isCapped"))
    updates["is_capped"] = "true" if is_capped else "false"
    if is_capped:
        if ev.get("maxCapacity") is not None:
            updates["max_capacity"] = int(ev["maxCapacity"])
        if ev.get("remainingCapacity") is not None:
            updates["remaining_capacity"] = int(ev["remainingCapacity"])

    # Cancellation. Partiful uses single-L "canceled" / double-L "cancellation"; we mirror it.
    is_canceled = ev.get("status") == "CANCELED"
    updates["canceled"] = "true" if is_canceled else "false"
    if is_canceled:
        if ev.get("canceledAt"):
            updates["canceled_at"] = yaml_val(ev["canceledAt"])
        canceled_by = ev.get("canceledBy") or {}
        if isinstance(canceled_by, dict) and canceled_by.get("id"):
            updates["canceled_by"] = yaml_val(canceled_by["id"])
        if ev.get("cancellationMessage"):
            # YAML-escape the cancellation message; can be multi-line.
            updates["cancellation_message"] = yaml_val(ev["cancellationMessage"])

    # Guest counts (richer fields)
    if ev.get("guestCount") is not None:
        updates["total_guest_count"] = int(ev["guestCount"])
    if ev.get("approvedGuestCount") is not None:
        updates["approved_guest_count"] = int(ev["approvedGuestCount"])

    # Image download
    image = ev.get("image") or {}
    img_url = image.get("url") or ""
    if img_url:
        fname, err = download_image(img_url, images_dir, event_id)
        if fname:
            updates["local_image"] = yaml_val(f"images/{fname}")
        else:
            updates["image_download_error"] = yaml_val(err or "unknown")

    new_block = patch_frontmatter(fm_block, updates)
    new_content = m.group(1) + new_block + m.group(3) + body
    if new_content != content:
        path.write_text(new_content, encoding="utf-8")
        return {"file": path.name, "status": "enriched", "owner_count": updates["owner_count"]}
    return {"file": path.name, "status": "unchanged"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--images-dir", required=True)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    events_dir = pathlib.Path(args.events)
    images_dir = pathlib.Path(args.images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(events_dir.glob("*.md"))
    if args.limit:
        files = files[: args.limit]

    print(f"[enrich] processing {len(files)} files, concurrency={args.concurrency}", flush=True)

    counts = {}
    done = 0
    log_path = events_dir.parent / "enrich.log"
    with open(log_path, "a") as logf:
        logf.write(f"\n=== run start {datetime.now().isoformat()} ===\n")
        with cf.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {pool.submit(process_one, f, images_dir): f for f in files}
            for fut in cf.as_completed(futures):
                r = fut.result()
                counts[r["status"]] = counts.get(r["status"], 0) + 1
                done += 1
                if done % 100 == 0 or done == len(files):
                    print(f"  [{done}/{len(files)}] {counts}", flush=True)
                logf.write(json.dumps(r) + "\n")
        logf.write(f"=== run done {datetime.now().isoformat()} {counts} ===\n")

    print(f"[enrich] done: {counts}")


if __name__ == "__main__":
    main()
