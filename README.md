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

LAYER 2 — DATA (Bright Data → Python seeder)
  scrape.py: Bright Data SDK scrapes montgomeryal.gov
  seed.py: Grok-4-Fast generates proposals → Rails runner inserts into Decidim
  60 seeded proposals across 10 civic categories (real Montgomery context)

LAYER 3 — AI (MCP Server, Python stdio)
  6 tools exposed to Claude Desktop:
  - get_proposals(category?, limit?)
  - classify_proposal(text) → Grok-4-Fast via OpenRouter
  - analyze_trends() → what Montgomery is talking about
  - recommend_action(topic) → city advisory + 311 routing
  - get_platform_summary() → full platform snapshot
  - get_montgomery_context(topic) → scraped civic data lookup

LAYER 4 — ADMIN BRIDGE (Claude Desktop + MCP)
  Mayor / city admin opens Claude Desktop
  → "What are citizens saying about public safety?"
  → Claude calls get_proposals() + analyze_trends()
  → Returns analysis + concrete recommendations
  This is the innovation. No civic platform has this.
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
│   ├── bugs.md            ← Issues log (20 bugs documented)
│   ├── api.md             ← Decidim GraphQL API reference
│   ├── data.md            ← DB schema
│   └── presentation/
│       └── pitch-deck.md  ← Hackathon pitch
├── seeder/
│   ├── venv/              ← Python virtualenv
│   ├── scrape.py          ← Bright Data → raw JSON
│   ├── seed.py            ← AI generation + Rails runner insertion
│   ├── requirements.txt
│   └── data/scraped/      ← 4 JSON files with real Montgomery data
└── mcp-server/
    ├── server.py          ← 6 MCP tools for Claude Desktop
    ├── decidim_client.py  ← GraphQL client (public reads)
    └── requirements.txt
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
