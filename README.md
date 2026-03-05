# Momentum MGM

> **Civic AI Platform for Montgomery, Alabama**
> World Wide Vibes Hackathon — March 5–9, 2026
> Inspired by Decidim (Barcelona) · Powered by AI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: Active Development](https://img.shields.io/badge/status-active-brightgreen)]()
[![Live](https://img.shields.io/badge/demo-mgm.styxcore.dev-blue)]()

---

## What is Momentum MGM?

Montgomery has no digital channel between citizens and city hall. Mayor Reed announces priorities at press conferences. Citizens respond... nowhere.

**Momentum MGM** is a civic participation platform — the same type used by Barcelona (40,000 participants), Quebec City, Montreal, and Brazil (36,000 proposals processed with AI) — deployed for Montgomery, Alabama, and extended with an AI layer that lets city administrators literally *talk to their city* through Claude.

Citizens submit proposals in plain language. AI classifies them across 10 civic categories. A live dashboard shows city hall what citizens actually care about. And an AI admin bridge (via MCP) lets decision-makers query, analyze, and act on citizen input in real time.

**The gap this fills:** Envision Montgomery 2040 + Reed's "Momentum" theme (State of the City 2026) describe exactly this kind of civic engagement infrastructure. It doesn't exist yet. We built it.

---

## Architecture Overview

```
LAYER 1 — PLATFORM (Decidim, native on ARM64)
  Citizens → Decidim UI → proposals, votes, comments
  Admin → Decidim dashboard → full participation management

LAYER 2 — SEEDER (Bright Data → Python → Decidim)
  scrape.py: Bright Data SDK scrapes montgomeryal.gov + SERP
  seed.py: Grok-4-Fast generates proposals → Rails runner inserts
  60+ seeded proposals across 10 civic categories (real Montgomery context)

LAYER 3 — CIVIC DATA LAKE (Bright Data SDK + Census ACS + pgvector)
  lake.py:   initial collection from Zillow, Yelp, Google Maps, Indeed, Census
  siphon.py: incremental refresh (daily/weekly/monthly via systemd timer)
  PostgreSQL civic_data schema + pgvector 1536d embeddings
  ~5000 records: properties, businesses, reviews, jobs, 14 years of Census data

LAYER 4 — AI ADMIN BRIDGE (MCP Server, 9 tools, Claude Desktop)
  9 tools exposed to Claude Desktop:
  - get_proposals()              → citizen voice (Decidim)
  - classify_proposal()         → AI classification
  - analyze_trends()            → platform analytics
  - recommend_action()          → city advisory + 311 routing
  - get_platform_summary()      → full Decidim snapshot
  - get_montgomery_context()    → scraped city data lookup
  - get_neighborhood_intelligence() → multi-source neighborhood report
  - semantic_civic_search()     → pgvector RAG across all data
  - get_neighborhood_velocity() → trend + projection (improving/declining)

  Mayor asks: "What's happening in West Montgomery?"
  Claude cross-references: 14 years Census + current Zillow/Yelp/Indeed
  + citizen proposals + velocity regression → actionable civic intelligence
```

---

## Proof of Concept

| Platform | City | Scale | Notes |
|---|---|---|---|
| Decidim | Barcelona | 40,000 participants, 10,000+ proposals | Original deployment |
| Decidim | Quebec City | Active | French-language civic engagement |
| Decidim | Montreal | Active | Major Canadian city |
| Brasil Participativo | Brazil (national) | 36,000 proposals | AI-classified with BERTopic + LLM |
| vTaiwan + Pol.is | Taiwan | National policy | Opinion clustering → real legislation |

Montgomery doesn't have this. We built it.

---

## Tech Stack

| Component | Technology | Notes |
|---|---|---|
| Civic Platform | Decidim 0.31 (Ruby on Rails) | Native install on ARM64 Debian |
| Database | PostgreSQL 15 (native) | `momentum` database on 127.0.0.1:5432 |
| Cache / Jobs | Redis 7 (Docker) | Sidekiq background jobs |
| AI — Generation | Grok-4-Fast via OpenRouter | Proposal generation + classification |
| AI — Fallback | Gemini 2.5 Flash (Google) | Automatic fallback if OpenRouter fails |
| Data Scraping | Bright Data SDK | montgomeryal.gov + Google SERP |
| MCP Server | Python (FastMCP stdio) | Claude Desktop ↔ Decidim bridge |
| Reverse Proxy | Nginx | mgm.styxcore.dev → localhost:3000 |
| Tunnel | Cloudflare | Public exposure via existing tunnel |
| Domain | styxcore.dev (owned) | Subdomain mgm. |

---

## Repository Structure

```
momentum-mgm/
├── README.md
├── docs/
│   ├── how_it_works.md    ← Full technical explanation (start here)
│   ├── architecture.md    ← System design + diagrams
│   ├── backend.md         ← MCP server + seeder details
│   ├── data.md            ← DB schema overview
│   ├── data_lake.md       ← Data lake full plan (sources, schema, siphon)
│   ├── bugs.md            ← Issues log + architecture divergences
│   ├── api.md             ← Decidim GraphQL API reference
│   └── presentation/
│       └── pitch-deck.md  ← Hackathon pitch
├── database/
│   └── 002_civic_data_lake.sql  ← civic_data schema + pgvector
├── seeder/
│   ├── venv/              ← Python virtualenv
│   ├── scrape.py          ← Bright Data → raw JSON (city context)
│   ├── seed.py            ← AI generation + Rails runner insertion
│   ├── lake.py            ← Data lake initial collection (all sources)
│   ├── siphon.py          ← Incremental refresh (run by systemd timer)
│   ├── requirements.txt
│   └── data/scraped/      ← 4 JSON files with real Montgomery data
├── mcp-server/
│   ├── server.py          ← 9 MCP tools for Claude Desktop
│   ├── decidim_client.py  ← GraphQL client (public reads)
│   └── requirements.txt
└── systemd/
    ├── momentum-lake.service  ← systemd service for siphon
    └── momentum-lake.timer    ← daily schedule
```

---

## Hackathon Timeline

| Day | Date | Focus | Status |
|---|---|---|---|
| 1 | Mar 5 | Decidim install + config + DB + Cloudflare | ✅ Done |
| 2 | Mar 6 | Bright Data scraper + seeder + 60 proposals | ✅ Done |
| 3 | Mar 7 | MCP Server — all 6 tools + end-to-end test | 🔄 In Progress |
| 4 | Mar 8 | Admin bridge polish + branding + Pol.is | ⏳ |
| 5 | Mar 9 | Final seed refresh + demo + submission | ⏳ |

---

## Team

| Name | Role |
|---|---|
| Alexandre Breton (StyxKnight) | Lead — Architecture, AI, MCP |

---

*Last updated: 2026-03-05*
