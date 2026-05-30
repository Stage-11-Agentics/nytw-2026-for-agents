# NY Tech Week Reference — agent instructions

You are working inside a flat-file mirror of [tech-week.com/calendar/nyc](https://www.tech-week.com/calendar/nyc). 1,410 events, one markdown file per event, plus an `INDEX.md` and a raw `manifest.json`.

## What you can do here

- **Filter by date, host, neighborhood, badge, or tag.** Frontmatter is machine-readable YAML.
- **Search descriptions.** `grep -l 'agent' events/*.md` works.
- **Shortlist for a specific user.** Use the user's stated interests and constraints (geography, time conflicts, lens) to score events. Write the shortlist to a new file (`picks-for-<name>.md`), do not edit individual event files unless instructed.
- **Build derivatives.** A "founder-only" list, a "no-suit-required" list, a calendar export, etc.

## What this repo is not

- **Not a guarantee of accuracy.** Events change. Always include the `rsvp_url` so users can verify. Don't claim a venue or time is current without flagging the crawl date.
- **Not a substitute for asking.** When in doubt about a user's preferences, ask. The dataset is dense; opinionated filtering helps more than dumping the full list.

## Crawl provenance

- `manifest.json` — raw extraction from the calendar page, exactly what the DOM contained at crawl time. Includes title, host, dateTime (string), neighborhood, badges, partiful URL.
- `events/*.md` — composed from both the calendar manifest and the per-event Partiful `__NEXT_DATA__` payload. Frontmatter is structured; body has the full description.
- See `README.md` for the dataset schema.
- `rounds/` + `CHANGES-<date>.md` — versioned fingerprints and the change report for each re-crawl. Diff two rounds with `scripts/round_diff.py`; validate a round against live Partiful with `scripts/spot_check.py`.

## Quirk: venues hide as events approach

As Tech Week nears, many hosts switch their Partiful page to show only an
`approximateLocation` (e.g. `"New York, NY"`) and drop the precise venue —
`locationInfo.mapsInfo.name` and `addressLines` go empty. So `venue_name` /
`venue_address` legitimately empty out between rounds (≈340 events did so
2026-05-21 → 2026-05-30); the empty value matches the live source, it is not a
crawl error. `neighborhood` still carries the general area. **Follow-up:**
`fetch.py`/`enrich.py` do not yet capture `locationInfo.mapsInfo.approximateLocation`
— wiring it in as a fallback would recover the coarse hint for these events.

## Quirk: the Partiful platform-admin user

The user ID `7DFu4rITofNzKIjA7hCx` appears in `owner_ids` for **1,362 of ~1,374 events** (≈99%). It is almost certainly a Partiful/TechWeek platform admin account auto-added to every event, not a real co-host. Downstream agents doing host analysis should filter it out:

```python
PLATFORM_ADMIN = "7DFu4rITofNzKIjA7hCx"
real_hosts = [h for h in owner_ids if h != PLATFORM_ADMIN]
```

The `owner_count` field includes this ID so the count matches what `partiful.com` shows visually. Filter at analysis time, not at storage time.

## Stage 11 / Atin-specific notes

This repo lives in `ideation/` under Stage 11. Phase 2 of the project layers Atin-specific recommendations on top of the base dataset:
- `TOP-PICKS.md` — curated shortlist filtered through the **agent orchestration + talent** lens.
- Per-event Stage 11 commentary is layered as an extra section in select event files, not in the frontmatter (so the base dataset stays neutral and shareable).

Keep these two surfaces separate. The base events/ should remain useful to anyone in the NY tech community; the picks layer is opinionated and Atin-specific.
