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

Citizens submit proposals in plain language. AI classifies them against Mayor Reed's stated priorities. A live dashboard shows city hall what citizens actually care about. And an AI admin bridge (via MCP) lets decision-makers query, analyze, and act on citizen input in real time.

**The gap this fills:** Envision Montgomery 2040 + Reed's "Momentum" theme (State of the City 2026) describe exactly this kind of civic engagement infrastructure. It doesn't exist yet. We built it.

---

## Architecture Overview

```
LAYER 1 — PLATFORM (Decidim, native on ARM64)
  Citizens → Decidim UI → proposals, votes, comments, initiatives
  + Pol.is module → opinion clustering (visual consensus)
  Admin → Decidim dashboard → full participation management

LAYER 2 — DATA (Bright Data → Python seeder)
  Scrape montgomeryal.gov public data
  → Generate realistic Montgomery proposals
  → Seed into Decidim via GraphQL API
  Platform is populated with real context from day 1

LAYER 3 — AI (MCP Server, Python ~300 lines)
  Tools exposed to Claude:
  - get_proposals(category?, district?)
  - classify_proposal(text) → Gemini Flash via OpenRouter
  - create_proposal(title, body)
  - get_clusters() → thematic trends
  - get_montgomery_context(topic) → scraped civic data
  - recommend_action(cluster_id) → city advisory

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
| Civic Platform | Decidim (Ruby on Rails) | Installed natively on ARM64 Debian |
| Opinion Layer | Pol.is via decidim-polis gem | Embedded in Decidim processes |
| Database | PostgreSQL 15 (existing) | New `momentum` database |
| Cache / Jobs | Redis 7 (existing) | Sidekiq background jobs |
| AI Classifier | Gemini Flash via OpenRouter | Cheap, fast, switchable |
| Data Scraping | Bright Data | montgomeryal.gov public data |
| MCP Server | Python (FastAPI or stdio) | Claude ↔ Decidim bridge |
| Reverse Proxy | Nginx + Nginx Proxy Manager | Existing setup |
| Auth | Authelia (existing) | Admin dashboard protection |
| Tunnel | Cloudflare (existing) | mgm.styxcore.dev public exposure |
| Domain | styxcore.dev (owned) | Subdomain mgm. |

---

## Repository Structure

```
momentum-mgm/
├── README.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── docs/
│   ├── architecture.md       ← System design, decisions, diagrams
│   ├── deployment.md         ← Full setup guide, prerequisites
│   ├── backend.md            ← MCP server + seeder documentation
│   ├── data.md               ← DB schema, Decidim data model
│   ├── api.md                ← Decidim GraphQL API reference
│   ├── bugs.md               ← Issues encountered + solutions
│   └── presentation/
│       ├── README.md
│       └── pitch-deck.md     ← Hackathon pitch content
├── seeder/                   ← Bright Data scraper + Decidim seeder
├── mcp-server/               ← MCP server (Claude ↔ Decidim)
└── config/                   ← Nginx vhost, env templates
```

---

## Hackathon Timeline

| Day | Date | Focus | Status |
|---|---|---|---|
| 1 | Mar 5 | Decidim install + config + DB + Cloudflare | 🔄 In Progress |
| 2 | Mar 6 | Bright Data scraper + Python seeder | ⏳ |
| 3 | Mar 7 | MCP Server — all tools + AI classifier | ⏳ |
| 4 | Mar 8 | Admin bridge polish + Pol.is integration | ⏳ |
| 5 | Mar 9 | Final seed + demo + submission | ⏳ |

---

## Team

| Name | Role |
|---|---|
| Alexandre Breton (StyxKnight) | Lead — Architecture, AI, MCP |

---

*Last updated: 2026-03-05*
