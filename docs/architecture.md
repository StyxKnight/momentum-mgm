# Architecture — Momentum MGM

## Overview

Momentum MGM is a civic participation platform built on Decidim extended with an AI layer via MCP (Model Context Protocol). Citizens engage through the Decidim interface; city administrators interact with Claude Desktop which uses our MCP server to query and analyze civic data in real time.

---

## System Diagram (current state — Day 2)

```
┌─────────────────────────────────────────────────────────────┐
│  CITIZENS (mgm.styxcore.dev)                                │
│  Submit proposals · Vote · Comment                          │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS (Cloudflare tunnel)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  NGINX (reverse proxy)                                      │
│  mgm.styxcore.dev → 172.21.0.1:3000 (Decidim on host)      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  DECIDIM 0.31 (Ruby on Rails, native ARM64, port 3000)      │
│  - 10 Participatory Processes (one per civic category)      │
│  - 60 seeded proposals (real Montgomery context)            │
│  - Proposals, votes, comments                               │
│  - GraphQL API at /api (PUBLIC READ-ONLY — no mutations)    │
│  - Admin dashboard at /admin                                │
└────────┬───────────────────────────────────────┬────────────┘
         │                                       │
         ▼                                       ▼
┌─────────────────┐                   ┌──────────────────────┐
│  PostgreSQL 15  │                   │  Redis 7             │
│  NATIVE on host │                   │  Docker container    │
│  DB: momentum   │                   │  port 6379 exposed   │
│  127.0.0.1:5432 │                   │  Sidekiq + sessions  │
└─────────────────┘                   └──────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  BRIGHT DATA PIPELINE (scrape.py + seed.py)                 │
│  Bright Data SDK → scrape montgomeryal.gov + SERP           │
│  Grok-4-Fast generates proposals from scraped context       │
│  Rails runner inserts via ActiveRecord (NOT GraphQL)        │
│  → 60 proposals across 10 categories ✅                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  MCP SERVER (Python, FastMCP, stdio — NOT HTTP port)        │
│  6 tools:                                                   │
│  - get_proposals(category?, limit?)                         │
│  - classify_proposal(text) → AI classification             │
│  - analyze_trends() → vote counts + top proposals          │
│  - recommend_action(topic) → city advisory + 311 routing   │
│  - get_platform_summary() → full snapshot                   │
│  - get_montgomery_context(topic) → scraped data lookup      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  OPENROUTER → GROK-4-FAST (primary)                         │
│  GOOGLE GEMINI 2.5 FLASH (automatic fallback)               │
│  Classification · Recommendations · Summaries               │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  ADMIN BRIDGE (Claude Desktop + MCP config)                 │
│  Mayor / city admin chats with Claude                       │
│  Claude calls MCP tools, analyzes proposals, advises        │
└─────────────────────────────────────────────────────────────┘
```

---

## What Is NOT Yet Built (planned Days 3-5)

- **Pol.is integration** (decidim-polis gem) — opinion clustering, Day 4
- **Auto-classification on submission** — Sidekiq job to classify proposals when citizens submit. Currently classification is on-demand via MCP tool only.
- **Proposal metadata storage** — category/summary from AI not yet stored back into Decidim. Currently computed live.
- **Demo user account** — citizen-facing test account for the demo flow

---

## Tech Stack Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Civic platform | Decidim (native install) | Proven at scale (Barcelona, Brazil, Quebec). Full feature set. |
| ARM64 strategy | Native install (not Docker) | Official Decidim Docker image is amd64-only. |
| AI primary | Grok-4-Fast via OpenRouter | Fast, cost-effective, already configured |
| AI fallback | Gemini 2.5 Flash (Google direct) | Auto fallback if OpenRouter fails |
| MCP protocol | FastMCP (stdio) | Native Claude Desktop integration. Not HTTP — runs as subprocess. |
| DB | PostgreSQL 15 (native) | Already running natively on host. NOT Docker. |
| Cache | Redis 7 (Docker, port 6379 exposed to host) | Already running for RPG Forum project. |
| Seeder writes | Rails runner (NOT GraphQL) | Decidim 0.31 GraphQL exposes 0 mutations. Direct ActiveRecord only. |
| Proposal generation | AI from scraped context | Real Montgomery data (streets, neighborhoods) → credible proposals |

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| 10 categories (not Reed's 5 priorities) | Civic taxonomy is stable; priorities change with mayors. Maps to 311 categories and city departments. |
| No `civic_data` table | Scraped data lives in JSON files. MCP reads from files directly. Simpler, no extra DB schema. |
| Rails runner for seeding | GraphQL is read-only. ActiveRecord is reliable and bypasses all API limitations. |
| GraphQL for MCP reads | Proposals are public. No auth needed. Clean separation: reads via API, writes via Rails. |
| OpenRouter as AI gateway | One key, multiple models, automatic model switching. Better than managing multiple API keys. |

---

## Data Flow — Proposal Lifecycle (current)

```
SEEDING (one-time):
  scrape.py → Bright Data → 4 JSON files
  seed.py → Grok-4-Fast → proposals JSON → Rails runner → Decidim DB

CITIZEN SUBMISSION (live):
  Citizen → Decidim UI → proposal saved in DB (no auto-classification yet)

ADMIN QUERY (via Claude Desktop):
  Admin asks Claude → Claude calls MCP tool → GraphQL query → Decidim DB
  → Claude analyzes + recommends → Admin acts
```

---

## Infrastructure

| Service | Location | Status | Role |
|---|---|---|---|
| PostgreSQL 15 | Native host 127.0.0.1:5432 | ✅ Up | Decidim DB (`momentum`) |
| Redis 7 | Docker rpg-forum-redis, port 6379 | ✅ Up | Sidekiq + sessions |
| Nginx | Docker rpg-nginx | ✅ Up | Reverse proxy |
| Cloudflare Tunnel | cloudflared service | ✅ Active | mgm.styxcore.dev |
| Decidim (Puma) | Native port 3000 | ✅ systemd | Civic platform |
| Sidekiq | Native | ✅ systemd | Background jobs |

---

*Last updated: 2026-03-05*
