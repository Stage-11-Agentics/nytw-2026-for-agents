#!/usr/bin/env python3
"""
Resolve Partiful user IDs to display names by fetching partiful.com/u/<id>.

Builds users.json (id → {name, bio, photo, socials, tags}) and patches each
event with a resolved_hosts list in the body.

Usage:
    python3 scripts/resolve_hosts.py --events events/ --out users.json
    python3 scripts/resolve_hosts.py --events events/ --out users.json --resume
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import pathlib
import re
import sys
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


def fetch_text(url: str, timeout: float = 25.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_user(html: str) -> dict | None:
    m = NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1)).get("props", {}).get("pageProps", {}).get("user")
    except json.JSONDecodeError:
        return None


def fetch_user(uid: str) -> tuple[str, dict | None, str | None]:
    url = f"https://partiful.com/u/{uid}"
    try:
        html = fetch_text(url)
    except urllib.error.HTTPError as e:
        return uid, None, f"HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError) as e:
        return uid, None, str(e)
    user = parse_user(html)
    if not user:
        return uid, None, "no user data"
    photo = user.get("photo") or {}
    photo_url = (photo.get("url") or "") if isinstance(photo, dict) else ""
    bio = user.get("bio") or {}
    bio_value = bio.get("value") if isinstance(bio, dict) else None
    bio_visibility = bio.get("visibility") if isinstance(bio, dict) else None
    return (
        uid,
        {
            "id": uid,
            "name": user.get("name"),
            "bio": bio_value,
            "bio_visibility": bio_visibility,
            "photo": photo_url,
            "is_managed": user.get("isManaged"),
            "on_partiful": user.get("onPartiful"),
            "socials": user.get("socials") or {},
            "tags": user.get("_tags") or [],
        },
        None,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()

    events_dir = pathlib.Path(args.events)
    unique_ids: set[str] = set()
    for f in events_dir.glob("*.md"):
        s = f.read_text(encoding="utf-8")
        m = re.search(r"owner_ids:\s*(\[[^\]]+\])", s)
        if m:
            try:
                ids = json.loads(m.group(1))
                unique_ids.update(ids)
            except json.JSONDecodeError:
                pass

    print(f"[resolve] {len(unique_ids)} unique user IDs", flush=True)

    # Resume mode: load existing users.json and skip ones already resolved
    existing: dict = {}
    out_path = pathlib.Path(args.out)
    if args.resume and out_path.exists():
        existing = json.load(open(out_path))
        print(f"[resolve] resuming with {len(existing)} already resolved", flush=True)

    todo = [uid for uid in unique_ids if uid not in existing]
    print(f"[resolve] fetching {len(todo)} new", flush=True)

    results = dict(existing)
    counts = {"ok": 0, "err": 0}
    log_path = events_dir.parent / "resolve.log"
    with open(log_path, "a") as logf:
        logf.write(f"\n=== run start {datetime.now().isoformat()} count={len(todo)} ===\n")
        with cf.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {pool.submit(fetch_user, uid): uid for uid in todo}
            done = 0
            for fut in cf.as_completed(futures):
                uid, user, err = fut.result()
                if user:
                    results[uid] = user
                    counts["ok"] += 1
                else:
                    counts["err"] += 1
                    logf.write(json.dumps({"uid": uid, "err": err}) + "\n")
                done += 1
                if done % 100 == 0 or done == len(todo):
                    print(f"  [{done}/{len(todo)}] ok={counts['ok']} err={counts['err']}", flush=True)
                    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
        logf.write(f"=== run done {counts} ===\n")

    # Final write
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"[resolve] wrote {out_path}: {counts}, total users={len(results)}")


if __name__ == "__main__":
    main()
