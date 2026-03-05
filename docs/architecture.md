# Architecture — Momentum MGM

## Overview

Momentum MGM is a civic intelligence platform built on three layers:
1. **Participation** — Decidim for citizen proposals, votes, comments
2. **Intelligence** — A live data lake (Bright Data + Census + city open data) with pgvector semantic search
3. **Admin Bridge** — Claude Desktop + MCP server giving city administrators natural language access to everything

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  CITIZENS (mgm.styxcore.dev)                                        │
│  Submit proposals · Vote · Comment                                  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTPS (Cloudflare tunnel)
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  NGINX (reverse proxy, Docker)                                      │
│  mgm.styxcore.dev → 172.21.0.1:3000                                 │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  DECIDIM 0.31 (Ruby on Rails, native ARM64, port 3000)              │
│  - 10 Participatory Processes (one per civic category)             │
│  - 60+ seeded proposals (real Montgomery context)                  │
│  - Proposals, votes, comments, admin dashboard                     │
│  - GraphQL API at /api (PUBLIC READ-ONLY — no mutations)           │
└──────────┬──────────────────────────────────────┬───────────────────┘
           │                                      │
           ▼                                      ▼
┌──────────────────┐                  ┌───────────────────────┐
│  PostgreSQL 15   │                  │  Redis 7              │
│  NATIVE host     │                  │  Docker container     │
│  127.0.0.1:5432  │                  │  port 6379 exposed    │
│                  │                  │  Sidekiq + sessions   │
│  DB: momentum    │                  └───────────────────────┘
│  ├─ public.*     │ ← Decidim schema (Rails-managed)
│  └─ civic_data.* │ ← Data lake schema (Python-managed)
│     + pgvector   │
└──────────┬───────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  DATA LAKE (civic_data schema + pgvector)                           │
│                                                                     │
│  Tables:                          Sources:                          │
│  ├─ properties   (Zillow)         Bright Data SDK datasets          │
│  ├─ businesses   (Yelp)           ZillowProperties  gd_lfqkr8wm... │
│  ├─ reviews      (GMaps+Yelp)     YelpBusinesses    gd_lgugwl05... │
│  ├─ jobs         (Indeed)         GoogleMapsReviews gd_luzfs1dn... │
│  ├─ census       (ACS API)        IndeedJobs        gd_l4dx9j9s... │
│  ├─ city_data    (opendata.mgm)   GlassdoorCompanies               │
│  ├─ embeddings   (pgvector 1536d) Census ACS API (free, 2010-2024) │
│  ├─ neighborhoods (reference)     City open data portal            │
│  └─ siphon_runs  (audit)                                           │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  SIPHON PIPELINE (lake.py + siphon.py)                              │
│  Bright Data SDK → normalize → geocode → upsert → embed            │
│  Scheduled by systemd timer:                                        │
│  - Indeed     → daily                                               │
│  - Yelp/GMaps → weekly                                              │
│  - Zillow     → monthly                                             │
│  - Census ACS → yearly                                              │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MCP SERVER (Python, FastMCP, stdio transport)                      │
│  9 tools:                                                           │
│  Existing (Decidim layer):                                          │
│  - get_proposals(category?, limit?)                                 │
│  - classify_proposal(text) → AI classification                     │
│  - analyze_trends() → vote counts + top proposals                  │
│  - recommend_action(topic) → city advisory + 311 routing           │
│  - get_platform_summary() → full Decidim snapshot                  │
│  - get_montgomery_context(topic) → scraped JSON lookup             │
│  New (Data Lake layer):                                             │
│  - get_neighborhood_intelligence(neighborhood) → multi-source      │
│  - semantic_civic_search(query, neighborhood?) → pgvector RAG      │
│  - get_neighborhood_velocity(neighborhood?) → trend + projection   │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AI LAYER                                                           │
│  OpenRouter → Grok-4-Fast (primary, all tools)                     │
│  Google Gemini 2.5 Flash (automatic fallback)                      │
│  OpenAI text-embedding-3-small (pgvector embeddings)               │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ADMIN BRIDGE (Claude Desktop + MCP config)                         │
│  Mayor / city admin chats with Claude in natural language           │
│  Claude calls MCP tools → queries Decidim + data lake              │
│  → Civic intelligence: history + present + velocity + projection   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## What Is Built (Day 1-2 ✅)

- Decidim 0.31 running natively on ARM64 at mgm.styxcore.dev
- 10 participatory processes (one per civic category)
- 60 seeded proposals (Bright Data + Grok-4-Fast)
- MCP server with 6 tools (Decidim layer)
- All docs audited and divergences documented

## What Is Being Built (Day 3-4 🔄)

- `database/002_civic_data_lake.sql` — civic_data schema + pgvector
- `seeder/lake.py` — initial data collection (Zillow, Yelp, GMaps, Indeed, Census)
- `seeder/siphon.py` — incremental refresh pipeline
- systemd timer for automated siphon
- MCP tools 7-9 (neighborhood intelligence, semantic search, velocity)
- Claude Desktop end-to-end test

## What Is NOT Yet Built (planned Day 4-5)

- **Pol.is integration** — opinion clustering (decidim-polis gem)
- **Auto-classification on submission** — Sidekiq job on citizen proposal submit
- **Demo citizen account** — for live demo flow
- **Civic health score dashboard** — visual overlay on Decidim

---

## Tech Stack Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Civic platform | Decidim 0.31 (native ARM64) | Proven at scale, full feature set, ARM64 Docker unavailable |
| Primary AI | Grok-4-Fast via OpenRouter | Fast, cost-effective, unified gateway |
| Fallback AI | Gemini 2.5 Flash (Google direct) | Auto-fallback if OpenRouter fails |
| Embeddings | text-embedding-3-small (OpenAI) | 1536d, cheap ($0.02/1M tokens), pgvector compatible |
| MCP transport | FastMCP stdio | Native Claude Desktop subprocess model |
| Data lake DB | PostgreSQL 15 + pgvector | Already running natively, pgvector already installed |
| Data sources | Bright Data SDK datasets | Pre-built structured datasets, 30-day trial, Python SDK |
| Historical data | US Census ACS API | Free, 2010-2024, census tract granularity |
| Neighborhood linking | Nominatim reverse geocoding | Free, no API key, lat/lon → neighborhood name |
| Seeder writes | Rails runner (NOT GraphQL) | Decidim 0.31 GraphQL = 0 mutations |
| Reads | GraphQL API | Public, no auth, clean separation |

---

## Infrastructure

| Service | Location | Status | Role |
|---|---|---|---|
| PostgreSQL 15 | Native host 127.0.0.1:5432 | ✅ Up | Decidim DB + civic_data lake |
| Redis 7 | Docker rpg-forum-redis, port 6379 | ✅ Up | Sidekiq + sessions |
| Nginx | Docker rpg-nginx | ✅ Up | Reverse proxy |
| Cloudflare Tunnel | cloudflared service | ✅ Active | mgm.styxcore.dev |
| Decidim (Puma) | Native port 3000 | ✅ systemd | Civic platform |
| Sidekiq | Native | ✅ systemd | Background jobs |
| momentum-lake.timer | systemd timer | ⏳ Day 3 | Automated siphon |

---

## Data Flow — Complete Picture

```
SEEDING (one-time):
  scrape.py → Bright Data → 4 JSON context files
  seed.py → Grok-4-Fast → proposals → Rails runner → Decidim DB

DATA LAKE (initial + ongoing):
  lake.py → Bright Data SDK (Zillow/Yelp/GMaps/Indeed) → civic_data tables
  lake.py → Census ACS API → civic_data.census
  siphon.py → incremental refresh per schedule → upsert + re-embed
  systemd timer → triggers siphon.py daily

CITIZEN (live):
  Citizen → Decidim UI → proposal saved in momentum.public

ADMIN QUERY (via Claude Desktop):
  Admin asks Claude → Claude calls MCP tool(s)
  → get_neighborhood_intelligence: queries civic_data + Decidim
  → semantic_civic_search: pgvector similarity across all sources
  → get_neighborhood_velocity: regression on Census ACS time series
  → Claude synthesizes: history + present + velocity + projection
  → Admin gets actionable civic intelligence
```

---

*Last updated: 2026-03-05*
