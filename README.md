# NY Tech Week 2026 — Reference

A community-maintained, agent-friendly markdown index of every Tech Week NYC event. Built so other agents (Claude, GPT, Gemini, custom workflows) can read, filter, and rank events without scraping the live calendar. **See [SKILL.md](SKILL.md) if you're an agent landing here.**

- **Dates:** June 1 – June 7, 2026
- **Source:** [tech-week.com/calendar/nyc](https://www.tech-week.com/calendar/nyc) (presented by a16z)
- **Coverage:** 1,381 unique events with full descriptions, hosts, dates, venues, and RSVP links. (7 events had Partiful 404s at crawl time and exist as stubs with manifest-derived data only.)
- **Last crawled:** 2026-05-21

## What this is

Tech Week's official calendar is a lazy-loaded React app. Reading it as a human is overwhelming; reading it programmatically requires browser automation. This repository is a flat-file mirror of that calendar, designed for two audiences:

1. **Other agents** — Each event is a self-contained markdown file with structured frontmatter. Point your agent at this directory and have it filter / rank / shortlist on your behalf.
2. **Humans skimming the list** — Browse `INDEX.md`, then dive into individual event files.

## Layout

```
ny-tech-week-reference/
├── README.md              ← you are here
├── CLAUDE.md              ← agent instructions for working with this dataset
├── INDEX.md               ← chronological + host + neighborhood + badge groupings (1,381 events)
├── TOP-PICKS.md           ← Stage 11 / Atin-specific shortlist (Phase 2 layer)
├── manifest.json          ← raw extraction from tech-week.com (one row per event)
├── scored.jsonl           ← per-event scoring (Stage 11 fit score, hits, category)
├── fetch.log              ← provenance: every fetch attempt with status
├── scripts/
│   ├── fetch.py           ← Partiful crawler (manifest → events/*.md)
│   ├── patch_metadata.py  ← refreshes host/neighborhood from manifest
│   ├── build_index.py     ← regenerates INDEX.md from events/
│   ├── score.py           ← scores each event for Stage 11 fit
│   └── build_top_picks.py ← regenerates TOP-PICKS.md from scored.jsonl
└── events/
    ├── 2026-06-01-0900-elevenlabs-ny-tech-week-popup.md
    ├── 2026-06-02-0915-what-quantum-actually-means-for-computing.md
    └── ... (1,381 files)
```

## Event file shape

Each `events/*.md` file has YAML frontmatter (machine-readable) followed by a human-readable body. See `events/_template.md` for the full schema.

Key frontmatter fields:

| Field | Example | Notes |
|-------|---------|-------|
| `title` | `"What Quantum Actually Means for Computing"` | Source of truth: Partiful |
| `date` | `2026-06-02` | ISO date in ET |
| `start_time` / `end_time` | `"9:15am ET"` | 12-hour format |
| `host` | `"IBM"` | Source: tech-week.com calendar card |
| `venue_name` | `"IBM One Madison Avenue"` | From Partiful's structured location |
| `venue_address` | `"1 Madison Ave, FL 2, New York, NY 10010"` | |
| `neighborhood` | `"Flatiron"` | |
| `rsvp_url` | `https://partiful.com/e/kQOkplcSkP79vs38zqvj` | Direct Partiful link |
| `badges` | `[Sponsored, Morning]` | From calendar card |
| `guest_action` | `APPLY` or `RSVP` | Whether host gatekeeps or accepts all |
| `at_capacity` | `false` | At crawl time |
| `visibility` | `public` | If `private`, description may be redacted |

## Why partiful

Every event on the Tech Week NYC calendar uses Partiful for RSVPs — that appears to be a platform requirement set by a16z. There are no Lu.ma, Eventbrite, or other RSVP sources in the dataset.

## Forking / re-crawling

The fetcher is at `scripts/fetch.py`. To re-crawl:

```bash
# Step A: refresh manifest.json from the calendar (requires c11 browser or a similar automation)
# Step B: regenerate event markdown
python3 scripts/fetch.py --manifest manifest.json --out events/
```

## License & attribution

Event metadata © respective hosts and tech-week.com / a16z. This repo is a fair-use index for personal and community use. If you're an event host and want your event removed or amended, open an issue (or message Atin at Stage 11).
