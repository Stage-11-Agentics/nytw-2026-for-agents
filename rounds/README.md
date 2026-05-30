# Crawl rounds

Versioned fingerprints of each crawl round, keyed by `event_id`, so any two
rounds can be diffed cleanly (the per-event markdown filenames are keyed by
date+time+slug, which makes a raw `git diff` of `events/` a poor change signal —
see `scripts/round_diff.py`).

- `round-<date>.json` — fingerprint of that round (one record per event_id:
  title, time, venue, host, capacity, cancellation, guest counts).
- `diff-<date>.json` — machine-readable diff vs the prior round.
- `../CHANGES-<date>.md` — the human-readable change report for that round.

## Re-crawl + diff workflow

```bash
# 0. snapshot the current (about-to-be-prior) round before re-crawling
python3 scripts/round_diff.py snapshot --events events/ --out rounds/round-<prev>.json

# 1..6. run the pipeline into a parallel dir (see README "re-crawling")
# 7. fingerprint the new round and diff
python3 scripts/round_diff.py snapshot --events events.new/ --out rounds/round-<new>.json
python3 scripts/round_diff.py diff --prev rounds/round-<prev>.json \
    --curr rounds/round-<new>.json --prev-label <prev> --curr-label <new> \
    --out CHANGES-<new>.md --json-out rounds/diff-<new>.json

# 8. validate against live Partiful before publishing
python3 scripts/spot_check.py --events events.new/ --sample 60 --out /tmp/spot.md
```
