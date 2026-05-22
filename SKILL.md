---
name: ny-tech-week-2026
description: A flat-file, agent-friendly mirror of every NY Tech Week 2026 event (June 1–7, NYC). Use when planning a Tech Week schedule, filtering events for a specific person/company, or analyzing the event landscape (top hosts, neighborhoods, capacity). 1,385 events with full descriptions, RSVP links, hero images, and 2,047 resolved host profiles.
---

# NY Tech Week 2026 — Agent Skill

You are working inside a community-maintained mirror of [tech-week.com/calendar/nyc](https://www.tech-week.com/calendar/nyc), restructured as flat markdown files so other agents can read, filter, and rank without scraping the live calendar.

## Dataset shape

```
ny-tech-week-reference/
├── README.md             ← human-readable overview
├── SKILL.md              ← you are here
├── INDEX.md              ← chronological + by-host + by-neighborhood listing
├── HOST-STATS.md         ← top 50 hosts + recurring co-host pairs
├── manifest.json         ← raw calendar extraction
├── users.json            ← 2,047 resolved Partiful profiles (id → name, bio, photo, socials, tags)
├── events/               ← 1,385 markdown files, one per event
└── images/               ← 1,344 hero images (PNG/JPG), keyed by event_id
```

Each `events/*.md` has YAML frontmatter and a body. Filename is `YYYY-MM-DD-HHMM-<slug>.md` — sortable by start time.

## Frontmatter quick reference

| Field | Type | Notes |
|-------|------|-------|
| `title` | string | From Partiful |
| `event_id` | string | Partiful event ID (last segment of RSVP URL) |
| `date`, `day` | string | ISO date + day name in ET |
| `start_time`, `end_time` | string | `"10:00am ET"` — pretty form |
| `start_iso`, `end_iso` | ISO 8601 | UTC, for date math |
| `host` | string | Calendar's joined host string (up to 2 names visible) |
| `owner_count` | int | True host count from Partiful (includes platform admin — see Quirks) |
| `owner_ids` | list[string] | All Partiful user IDs; join with `users.json` for names + bios |
| `venue_name`, `venue_address` | string | From Partiful's structured location |
| `neighborhood` | string | NYC neighborhood like `Chelsea`, `Midtown`, `Virtual (NYC)` |
| `rsvp_url`, `public_short_url` | URL | Partiful links |
| `google_maps` | URL | Pre-formed maps query |
| `is_capped`, `max_capacity`, `remaining_capacity` | bool / int | When the host capped the guestlist |
| `going_guest_count`, `total_guest_count`, `approved_guest_count` | int | Guest count at crawl time (2026-05-21) |
| `at_capacity` | bool | Whether RSVPs are currently closed |
| `canceled` | bool | `true` if the host marked the event canceled on Partiful |
| `canceled_at` | ISO 8601 | When cancellation was logged (only when `canceled: true`) |
| `canceled_by` | string | Partiful user ID that triggered the cancellation |
| `cancellation_message` | string | The host's note explaining why (verbatim, may be multi-line) |
| `guest_action` | `"APPLY"` or `"RSVP"` | APPLY = hosts approve; RSVP = open |
| `visibility` | string | `"public"` for the entire dataset |
| `badges` | list[string] | `["Sponsored"]`, `["Morning"]`, etc. |
| `image` | URL | Partiful Firebase image URL (may expire) |
| `local_image` | string | Path to archived image in `images/` (use this, not `image`) |
| `fetch_status` | `"ok"` or `"failed"` | 7 events are stubs (Partiful 404'd at crawl time) |

## Body shape

```
# {title}
![{title}](images/{event_id}.png)

**Hosts:** {calendar host string} _(+N more on Partiful)_
**When:** {pretty date}
**Where:** {venue · address · neighborhood}
**Capacity:** capped at N · X taken, Y remaining
**Going:** N of M
**Access:** apply / hosts approve
**RSVP:** {url}
**Map:** {google maps url}

### Hosts on Partiful

- [{name}](https://partiful.com/u/{id}) — _{bio}_
- [{name}](https://partiful.com/u/{id})
- _(plus Partiful platform admin auto-added to most events)_

## Description

{full Partiful description, verbatim}

---

[Apply on Partiful →]({url})
```

## Quirks worth knowing

1. **The platform admin user.** `7DFu4rITofNzKIjA7hCx` appears in `owner_ids` for ~99% of events (1,362 of 1,374). Treat it as noise — it's an automated TechWeek/Partiful account, not a real host. Filter at analysis time:
   ```python
   real_hosts = [oid for oid in owner_ids if oid != "7DFu4rITofNzKIjA7hCx"]
   ```
   `owner_count` includes it to match Partiful's UI count.

2. **Capacity fields only present when capped.** If `is_capped: false`, `max_capacity` and `remaining_capacity` will be absent. Use `going_guest_count` / `total_guest_count` for uncapped events.

3. **7 stub events** (`fetch_status: failed`) had their Partiful pages 404 at crawl time. Frontmatter is sparse, body is a stub with the RSVP URL. They still exist in `events/` for completeness — handle by checking `fetch_status` first.

4. **Calendar host string is truncated.** `host: "Foo, Bar"` shows up to 2 hosts. For the true list, look at `### Hosts on Partiful` in the body, or join `owner_ids` against `users.json`.

5. **One outlier date.** One event (`Pitch and Rum`) is dated 2026-06-11, outside the official June 1–7 window. It's on tech-week.com's calendar so it stays.

6. **Cancellations stay in the dataset.** When a host marks an event `CANCELED` on Partiful, we keep the file (so the URL stays resolvable, the data stays diff-able across crawls, and downstream agents can see *what* was cancelled and *why*) but flag it loudly: `canceled: true` in frontmatter, a `⚠ CANCELED` banner at the top of the body with the host's `cancellation_message`. Filter at analysis time:
   ```python
   live_events = [f for f in events if not f.get("canceled")]
   ```

7. **Crawl provenance.** Snapshotted 2026-05-21. Event details, RSVP availability, and guest counts may have drifted since.

## Common queries

### "What events are happening on Tuesday June 2 in SoHo?"

```bash
grep -l 'date: 2026-06-02' events/*.md \
  | xargs grep -l 'neighborhood: "SoHo"'
```

### "Which events focus on agent orchestration?"

```bash
grep -l -i 'agent' events/*.md \
  | xargs grep -l -iE '(orchestrat|autonomous|multi-?agent|MCP)'
```

### "Top 10 hosts by event count"

See `HOST-STATS.md`, or compute from `events/*.md` `owner_ids` joined with `users.json`:
```python
import json, re, pathlib, collections
users = json.load(open("users.json"))
counts = collections.Counter()
for f in pathlib.Path("events").glob("*.md"):
    m = re.search(r'owner_ids:\s*(\[[^\]]+\])', f.read_text())
    if m:
        for uid in json.loads(m.group(1)):
            if uid != "7DFu4rITofNzKIjA7hCx":
                counts[uid] += 1
for uid, n in counts.most_common(10):
    print(n, users.get(uid, {}).get("name"))
```

### "Build a shortlist for a specific person"

Score each event against the person's interests (use their bio, role, or stated themes as keyword seeds), then pick top N per day. See `scripts/score.py` for the pattern used to score events for Atin Woodard / Stage 11. **Do not modify individual event files** for a person-specific shortlist — write the picks to a new file like `picks-for-<name>.md`. Keep `events/` neutral so it stays useful to everyone.

### "Show me all cancelled events and why"

```bash
grep -l '^canceled: true' events/*.md | while read f; do
  title=$(grep -m1 '^title:' "$f" | sed 's/title: //; s/^"//; s/"$//')
  msg=$(grep -m1 '^cancellation_message:' "$f" || true)
  printf "%s\n  %s\n  %s\n\n" "$title" "$f" "$msg"
done
```

### "Find events at risk of filling up"

Where `is_capped: true` and `remaining_capacity` is small relative to `max_capacity`:
```python
import re, json, pathlib
for f in pathlib.Path("events").glob("*.md"):
    s = f.read_text()
    if re.search(r"is_capped:\s*true", s):
        max_c = int(re.search(r"max_capacity:\s*(\d+)", s).group(1))
        rem = int(re.search(r"remaining_capacity:\s*(\d+)", s).group(1))
        if rem / max_c < 0.15:
            title = re.search(r'title:\s*"([^"]+)"', s).group(1)
            print(f"{rem}/{max_c} remaining: {title}")
```

## Re-crawling

NYTW data shifts daily. To refresh:

1. Open the calendar in a browser; scroll through the full page (or use `c11` / Playwright to script the scroll).
2. Run `scripts/fetch.py` against the regenerated manifest.
3. Run `scripts/enrich.py` to refresh capacity + image data.
4. Run `scripts/resolve_hosts.py` to re-resolve any new host IDs.
5. Run `scripts/render_body.py` to regenerate the rendered markdown.
6. Run `scripts/build_index.py` and `scripts/host_stats.py`.

Each step is idempotent — re-runnable without duplication.

## What this dataset is not

- **Not authoritative.** Always include `rsvp_url` so humans can verify. `tech-week.com` is the source of truth; this repo is a convenience layer.
- **Not real-time.** Guest counts, capacity, and even event existence drift after the crawl date.
- **Not opinionated.** `events/` is neutral. Person-specific picks belong in separate files.

## Attribution

Event metadata © respective hosts and tech-week.com / a16z. Partiful images © Partiful + respective uploaders. This dataset is shared under fair-use for community planning and agent tooling.
