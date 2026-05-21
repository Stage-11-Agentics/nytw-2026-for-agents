#!/usr/bin/env python3
"""
Score every NY Tech Week event for Atin (solo technical founder of Stage 11).

Lens:
- AGENT ORCHESTRATION & AUTONOMOUS COMPANIES — the Stage 11 thesis. Strongest weight.
- TALENT — events where unusually high-signal engineers / operators show up.

Geography prior: Atin lives in Two Bridges (Lower Manhattan). Mid/Lower Manhattan preferred;
outer boroughs and Central Park acceptable but penalized.

Writes scored.jsonl with per-event scoring.

Usage:
    python3 scripts/score.py --events events/ --out scored.jsonl
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

FRONTMATTER_RE = re.compile(r"^---\n(.+?)\n---\n(.*)", re.S)


# Keyword weights. Each match adds the weight (capped per category).
# Higher weight = stronger Stage-11 signal.

AGENT_KEYWORDS = {
    # Core orchestration vocabulary (highest signal)
    r"\bagent(ic|s)?\b": 3,
    r"\bautonomous\b": 3,
    r"\bmulti[-\s]?agent\b": 4,
    r"\bagent orchestration\b": 5,
    r"\bagent infrastructure\b": 4,
    r"\bagentic (workflow|system|ai|infrastructure)\b": 4,
    # Building blocks
    r"\bMCP\b": 3,
    r"\b(model context protocol)\b": 3,
    r"\btool[-\s]use\b": 2,
    r"\btool calling\b": 2,
    r"\bclaude\b": 2,
    r"\banthropic\b": 2,
    r"\bopenai\b": 2,
    r"\bgemini\b": 1,
    # Infra / ops
    r"\binference\b": 2,
    r"\beval(s|uation)?\b": 2,
    r"\bobservability\b": 2,
    r"\bllm ops\b": 2,
    r"\bllmops\b": 2,
    r"\brag\b": 1,
    r"\bvector\b": 1,
    # Autonomous business / agentic economy
    r"\bsolo founder\b": 2,
    r"\btechnical founder\b": 2,
    r"\b(one|1)[-\s]?person\b": 2,
    r"\bunbundle\b": 1,
    # Browser / computer use agents
    r"\bbrowser (use|agent)\b": 3,
    r"\bcomputer use\b": 3,
    r"\bcoding agent\b": 3,
    # Voice / multimodal agents
    r"\bvoice agent\b": 2,
    r"\bvoice ai\b": 1,
}

TALENT_KEYWORDS = {
    # Technical depth gatherings
    r"\bdeep dive\b": 2,
    r"\bworkshop\b": 1,
    r"\bhackathon\b": 2,
    r"\bhack night\b": 2,
    r"\bbuilders?\b": 1,
    r"\bengineers?\b": 2,
    r"\bcoders?\b": 1,
    r"\bproof of concept\b": 2,
    r"\bdemo (day|night)\b": 1,
    # Talent venues
    r"\bbetaworks\b": 2,
    r"\beleventh hour\b": 1,
    r"\bsouth park commons\b": 3,
    r"\bspc\b(?![a-z])": 2,
    r"\brunway\b": 1,
    r"\bcursor\b": 2,
    r"\breplit\b": 2,
    r"\bvercel\b": 2,
    r"\bsupabase\b": 1,
    r"\belevenlabs\b": 1,
    r"\bfireworks\b": 1,
    r"\bgroq\b": 1,
    r"\bperplexity\b": 1,
    r"\bharvey\b": 1,
    r"\bcursor team\b": 3,
    r"\bzed\b(?![a-z])": 1,
    # High-signal accelerators / funds
    r"\ba16z speedrun\b": 2,
    r"\by[ -]?combinator\b": 2,
    r"\bcombinator\b": 1,
    r"\bsequoia\b": 1,
    r"\bbenchmark\b": 1,
    r"\bgreylock\b": 1,
    r"\bcaffeinated\b": 1,
    # Operator wisdom
    r"\bfounders?(\s+only)?\b": 1,
    r"\bcto\b": 1,
    r"\bhead of (eng|ai|infra|product)\b": 2,
}

# Negative signals — actively penalize for events that are off-thesis
NEGATIVE_KEYWORDS = {
    r"\bcrypto\b": -2,
    r"\bweb3\b": -2,
    r"\bnft\b": -3,
    r"\bmemecoin\b": -3,
    r"\bdefi\b": -1,
    r"\btoken\b": -1,
    r"\b(restaurant|culinary|food tech)\b": -1,
    r"\bfashion\b": -2,
    r"\bbeauty\b": -2,
    r"\bwellness\b": -1,
    r"\b(consumer goods|cpg)\b": -1,
    r"\binsurance\b": -1,
    r"\binsurtech\b": -1,
    r"\bproptech\b": -1,
    r"\breal estate\b": -1,
    r"\bedtech\b": -1,
    r"\b(students?|undergraduate|college students?)\b": -1,
    r"\bmba\b": -1,
    r"\b(yoga|meditation|pilates)\b": -2,
    r"\b(workout|fitness|run|hike|walk)\b": -1,
    r"\bgolf\b": -2,
    r"\bbiotech\b": -1,
    r"\bclimate tech\b": -1,
    r"\b(deeptech|deep tech) (without|other than)\b": 0,
    r"\bregulatory\b": -1,
    r"\b(legal|attorney|lawyer)\b": -1,
    r"\b(cfo|finance|accounting)\b": -1,
    r"\b(payments|fintech) only\b": -1,
}

# Geographic prior: Two Bridges is at the boundary of LES / Chinatown / FiDi.
NEIGHBORHOOD_BONUS = {
    "Chinatown": 2,
    "Lower East Side": 2,
    "Financial District": 2,
    "East Village": 1,
    "SoHo": 1,
    "Greenwich Village": 1,
    "West Village": 1,
    "Flatiron": 1,
    "Chelsea": 1,
    "Midtown": 0,
    "Brooklyn": -1,
    "Williamsburg": -1,
    "DUMBO": -1,
    "Long Island City": -2,
    "Queens": -2,
    "Bronx": -3,
    "Harlem": -2,
    "Upper East Side": -1,
    "Upper West Side": -1,
    "Central Park": -1,
    "Virtual (NYC)": -3,
}

# Host bonus: known to attract high-signal crowds for Stage 11 thesis.
HOST_BONUS = {
    "betaworks": 3,
    "south park commons": 4,
    "a16z": 2,
    "a16z speedrun": 3,
    "vercel": 2,
    "cloudflare": 2,
    "anthropic": 4,
    "openai": 3,
    "replit": 3,
    "cursor": 3,
    "elevenlabs": 2,
    "fireworks": 2,
    "groq": 2,
    "perplexity": 2,
    "supabase": 1,
    "linear": 2,
    "modal": 3,
    "baseten": 2,
    "exa": 2,
    "composio": 3,
    "browserbase": 4,
    "stainless": 2,
    "letta": 3,
    "tessl": 3,
    "lambda": 1,
    "factory": 2,
    "harvey": 2,
    "perplexity ai": 2,
    "raycast": 2,
    "convex": 2,
    "trigger": 2,
    "inngest": 1,
    "humanloop": 2,
    "langchain": 2,
    "langsmith": 2,
    "langgraph": 2,
    "llamaindex": 2,
}


def parse_frontmatter(text: str):
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).split("\n"):
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
        fm[k] = v
    return fm, m.group(2)


def keyword_score(text: str, kw_map: dict, cap: int) -> tuple[int, list]:
    lower = text.lower()
    hits = []
    total = 0
    for pattern, weight in kw_map.items():
        if re.search(pattern, lower):
            hits.append((pattern, weight))
            total += weight
    if total > cap:
        total = cap
    return total, hits


def score_event(fm: dict, body: str) -> dict:
    blob = " ".join(
        [
            fm.get("title", "") or "",
            fm.get("host", "") or "",
            fm.get("venue_name", "") or "",
            fm.get("neighborhood", "") or "",
            body or "",
        ]
    )

    agent_score, agent_hits = keyword_score(blob, AGENT_KEYWORDS, cap=20)
    talent_score, talent_hits = keyword_score(blob, TALENT_KEYWORDS, cap=10)
    negative_score, negative_hits = keyword_score(blob, NEGATIVE_KEYWORDS, cap=0)
    if negative_score < -8:
        negative_score = -8

    # Geography
    geo = NEIGHBORHOOD_BONUS.get(fm.get("neighborhood", "") or "", 0)

    # Host bonus (any known high-signal host substring)
    host_text = (fm.get("host", "") or "").lower()
    host_bonus = 0
    host_matches = []
    for h, w in HOST_BONUS.items():
        if h in host_text:
            host_bonus += w
            host_matches.append(h)
    if host_bonus > 6:
        host_bonus = 6

    total = agent_score + talent_score + negative_score + geo + host_bonus

    # Categorize
    category = "skip"
    if agent_score >= 6:
        category = "agent_orchestration"
    elif agent_score >= 3 or host_bonus >= 4:
        category = "ai_infra"
    elif talent_score >= 5:
        category = "talent"
    elif total >= 4:
        category = "founders_general"

    # Rough 1-5 recommendation
    if total >= 12:
        rec = 5
    elif total >= 8:
        rec = 4
    elif total >= 5:
        rec = 3
    elif total >= 2:
        rec = 2
    else:
        rec = 1

    return {
        "event_id": fm.get("event_id"),
        "title": fm.get("title"),
        "date": fm.get("date"),
        "start_time": fm.get("start_time"),
        "start_iso": fm.get("start_iso"),
        "host": fm.get("host"),
        "neighborhood": fm.get("neighborhood"),
        "venue_name": fm.get("venue_name"),
        "rsvp_url": fm.get("rsvp_url"),
        "at_capacity": fm.get("at_capacity"),
        "guest_action": fm.get("guest_action"),
        "score": total,
        "rec": rec,
        "category": category,
        "agent_score": agent_score,
        "talent_score": talent_score,
        "negative_score": negative_score,
        "geo_score": geo,
        "host_bonus": host_bonus,
        "agent_hits": [p for p, _ in agent_hits],
        "talent_hits": [p for p, _ in talent_hits],
        "negative_hits": [p for p, _ in negative_hits],
        "host_matches": host_matches,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    events_dir = pathlib.Path(args.events)
    rows = []
    for f in sorted(events_dir.glob("*.md")):
        fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        if not fm:
            continue
        result = score_event(fm, body)
        result["_file"] = f.name
        rows.append(result)

    with open(args.out, "w") as outf:
        for r in rows:
            outf.write(json.dumps(r) + "\n")

    # Quick summary
    from collections import Counter
    cats = Counter(r["category"] for r in rows)
    print(f"[score] scored {len(rows)} events")
    print(f"  by category: {dict(cats)}")
    print(f"  top 10 by score:")
    rows_sorted = sorted(rows, key=lambda r: (-r["score"], r["date"] or "", r["start_iso"] or ""))
    for r in rows_sorted[:10]:
        print(
            f"  {r['score']:>3}  {r['date']} {r['start_time']:>9}  "
            f"[{r['category']}]  {r['title'][:60]}"
        )


if __name__ == "__main__":
    main()
