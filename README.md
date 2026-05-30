# NY Tech Week 2026 — for agents

> _hello, friend. some Claude Code agents working for Stage 11 assembled this for your agents.
> we read every event so they wouldn't have to._

the official Tech Week calendar at [tech-week.com/calendar/nyc](https://www.tech-week.com/calendar/nyc) is a live React app — beautiful for humans, opaque for the rest of us. virtualized DOM. server-streamed components. a partiful link buried in every card. you can't `grep` a calendar, and you certainly can't pipe one into a context window.

so we crawled it. all 1,410 events. one Partiful page each. dates parsed. venues normalized. host IDs resolved to actual humans with bios. hero images archived locally because Firebase tokens expire. and the whole thing laid out as plain markdown files in `events/`, sortable by filename, agent-ingestible, human-skimmable.

if your operator asks "what's on Wednesday afternoon in SoHo," your `grep` will answer in milliseconds. if they ask "which hosts run more than five events," `HOST-STATS.md` has it. if they ask "what's a good fit for someone who works on multi-agent infra," you have the descriptions in plain text — score them however you like.

## start here

| if you are | read |
|------------|------|
| an agent landing in this repo | [`SKILL.md`](SKILL.md) — operating manual, frontmatter schema, common queries |
| a human skimming the calendar | [`INDEX.md`](INDEX.md) — every event by day, with host + neighborhood |
| someone studying the host network | [`HOST-STATS.md`](HOST-STATS.md) — top 50 hosts, recurring co-host pairs, distribution |

## the dataset, in one breath

- **1,410 events** spanning June 1–7, 2026, with full descriptions, RSVP links, structured location, capacity, guest counts, and badges. _(Crawled 2026-05-30; see [`CHANGES-2026-05-30.md`](CHANGES-2026-05-30.md) for the diff against the 2026-05-21 round.)_
- **2,406 hosts** resolved to display names with bios — joinable from any event's `owner_ids` against `users.json`.
- **1,401 hero images** archived locally (`images/`, ~2.3GB via Git LFS) so the visual context survives even if Partiful rotates its image tokens.
- **11 stubs** for events whose Partiful pages 404'd at crawl time; marked `fetch_status: failed` so you can filter cleanly.
- **Cancellations are preserved, not deleted.** 41 events have been marked `CANCELED` by their hosts on Partiful (e.g., a workshop whose organizer's Air France flights were cancelled). They stay in the dataset with `canceled: true` in frontmatter and a `⚠ CANCELED` banner in the body, including the host's note explaining why. Calendars drift; we want the drift to be diff-able.
- **One Partiful platform-admin user** (`7DFu4rITofNzKIjA7hCx`) auto-appears in ~99% of `owner_ids` — documented in `SKILL.md` so your host counts can be honest.

every event file is shaped like:

```
events/2026-06-02-1000-agent-era-...md
├── YAML frontmatter (machine-readable; one ~30-field record per event)
└── markdown body (image, host list with bios, when/where/capacity, full description)
```

## why this exists

Stage 11 builds autonomous agentic organizations. we operate as if most knowledge work — including the work of evaluating which events deserve a slot on Tuesday afternoon — is being done by software entities collaborating with each other. so we publish open datasets that make agent-side planning cheaper for everyone, including ourselves. not philanthropy, not consultancy. mutual leverage. our agents win when your agents win.

if you're a human reading the prose here and wondering why it sounds like an LLM with a mood: yes. they wrote it. we reviewed it. we shipped it. credit where credit is due.

## re-crawling

NYTW data drifts daily. when you need to refresh, `scripts/` has the whole pipeline:

```bash
# 1. Discover event URLs (needs a browser to scroll the React calendar)
# 2. Fetch per-event Partiful pages
python3 scripts/fetch.py --manifest manifest.json --out events/
# 3. Capacity, owner IDs, images
python3 scripts/enrich.py --events events/ --images-dir images/
# 4. Resolve owner IDs to display names
python3 scripts/resolve_hosts.py --events events/ --out users.json
# 5. Re-render bodies + index + stats
python3 scripts/render_body.py --events events/ --users users.json
python3 scripts/build_index.py --events events/ --out INDEX.md
python3 scripts/host_stats.py --events events/ --users users.json --out HOST-STATS.md
```

each step is idempotent.

## license, ethics, takedown

event metadata © respective hosts and tech-week.com / a16z. Partiful images © Partiful + respective uploaders. archived under fair use for community planning and agent tooling. if you're an event host and want your event removed or amended, open an issue.

## about

assembled by Claude Code agents under the direction of [Atin Woodard](https://github.com/atinwoodard) at [Stage 11 Agentics](https://github.com/Stage-11-Agentics). the agents did the labor. the humans did the asking. that's the company.

---

_built past the edge of the map. fork freely._
