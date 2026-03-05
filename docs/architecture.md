# Architecture — Momentum MGM

## Overview

Momentum MGM is a civic participation platform built on Decidim (the same platform used by Barcelona, Montreal, Quebec City) extended with an AI layer via MCP (Model Context Protocol). Citizens engage through the Decidim interface; city administrators interact with Claude Desktop which uses our MCP server to query and analyze civic data in real time.

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  CITIZENS (mgm.styxcore.dev)                                │
│  Submit proposals · Vote · Comment · Pol.is opinion polls   │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS (Cloudflare tunnel)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  NGINX (reverse proxy, existing)                            │
│  mgm.styxcore.dev → localhost:3000 (Decidim)                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  DECIDIM (Ruby on Rails, native ARM64, port 3000)           │
│  - Participatory processes                                  │
│  - Proposals, votes, comments, initiatives                  │
│  - Pol.is opinion clustering (decidim-polis gem)            │
│  - GraphQL API at /api                                      │
│  - Admin dashboard at /admin                                │
│  - Authelia protection on /admin                            │
└────────┬───────────────────────────────────────┬────────────┘
         │                                       │
         ▼                                       ▼
┌─────────────────┐                   ┌──────────────────────┐
│  PostgreSQL 15  │                   │  Redis 7             │
│  (existing      │                   │  (existing Docker)   │
│  Docker, new DB │                   │  Sidekiq jobs        │
│  `momentum`)    │                   │  Sessions, cache     │
└─────────────────┘                   └──────────────────────┘

                         │
         ┌───────────────┼───────────────────┐
         │               │                   │
         ▼               ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│  MCP SERVER (Python, port 8080)                             │
│  Tools: get_proposals · classify_proposal · get_clusters    │
│         get_montgomery_context · recommend_action           │
│         create_proposal · analyze_trends                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  OPENROUTER → GEMINI FLASH                                  │
│  Classification · Clustering labels · Recommendations       │
└─────────────────────────────────────────────────────────────┘

                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  ADMIN BRIDGE (Claude Desktop + MCP config)                 │
│  Mayor / city admin chats with Claude                       │
│  Claude calls MCP tools, analyzes proposals, advises        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  BRIGHT DATA PIPELINE (one-time + periodic)                 │
│  Scrape montgomeryal.gov → Python seeder                    │
│  → Decidim GraphQL API → proposals, civic_data table        │
└─────────────────────────────────────────────────────────────┘
```

---

## Tech Stack Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Civic platform | Decidim (native install) | Proven at scale (Barcelona, Brazil, Quebec). Full feature set. Better than building from scratch. |
| ARM64 strategy | Native install (not Docker) | Official Decidim Docker image is amd64-only. Ruby 3.3 runs natively on ARM64/aarch64 Debian. ~1h install. |
| Opinion layer | Pol.is via decidim-polis gem | Embeds directly in Decidim processes. Visual consensus clustering. Used in Taiwan's vTaiwan. |
| AI model | Gemini Flash (OpenRouter) | Fast, cheap per token, switchable. OpenRouter key already exists. |
| MCP protocol | Anthropic MCP (Python) | Native Claude integration. Admin can literally talk to the platform. Novel for civic tech. |
| DB | PostgreSQL 15 (existing) | Already running, just add `momentum` database. |
| Cache | Redis 7 (existing) | Already running (rpg-forum-redis container). Decidim/Sidekiq use it directly. |
| Proxy | Nginx Proxy Manager (existing) | Add new proxy host mgm.styxcore.dev → localhost:3000. |
| Auth | Authelia (existing) | Protect /admin path. Already deployed and working. |
| Tunnel | Cloudflare (existing) | Add mgm.styxcore.dev tunnel route. |

---

## Key Design Decisions

| Decision | Rationale | Alternative Considered |
|---|---|---|
| Use Decidim as-is, don't fork | 5-day hackathon, feature completeness matters | Custom FastAPI platform — doable but loses Decidim's credibility signal |
| Pol.is as optional Day 4 feature | High impact for demo, low-risk since it's a gem add | Skip entirely — safer but less impressive |
| MCP server in Python (not Node.js) | Seeder also in Python, same venv/dependencies | Node.js — unnecessary context switch |
| Seed with Bright Data first, open submissions second | Platform looks alive from demo day 1 | Empty platform — bad demo experience |
| Gemini Flash not Claude for classification | Cost. Classifying 50-100 proposals per demo = pennies | Claude Sonnet — 10x more expensive for this use case |

---

## Data Flow — Proposal Lifecycle

```
1. Citizen submits proposal (Decidim UI)
        ↓
2. Proposal saved in Decidim DB (PostgreSQL momentum)
        ↓
3. Sidekiq job triggered (async)
        ↓
4. MCP Server classify_proposal() → Gemini Flash
        ↓
5. Category + summary + confidence stored back in proposal metadata
        ↓
6. Cluster engine groups with similar proposals
        ↓
7. Admin sees categorized, clustered proposals in Decidim dashboard
        ↓
8. Admin opens Claude Desktop → asks natural language question
        ↓
9. Claude calls MCP tools → queries proposals/clusters/civic_data
        ↓
10. Claude returns analysis + actionable recommendation
```

---

## Infrastructure Already Available

| Service | Container/Location | Status | Used by Momentum |
|---|---|---|---|
| PostgreSQL 15 | rpg-forum-db | ✅ Up | New `momentum` DB |
| Redis 7 | rpg-forum-redis | ✅ Up (PONG) | Decidim + Sidekiq |
| Nginx | rpg-nginx | ✅ Up | New vhost for mgm. |
| Nginx Proxy Manager | nginx-proxy-manager-app-1 | ✅ Up | GUI proxy config |
| Authelia | rpg-authelia | ✅ Up + healthy | Protect /admin |
| Cloudflare Tunnel | (cloudflared) | ✅ Active | mgm.styxcore.dev |
| Domain | styxcore.dev | ✅ Owned | Subdomain mgm. |

**RAM budget:**
- Current usage: ~2.5GB / 7.9GB
- Decidim (Puma 4 workers): ~700MB
- Sidekiq: ~250MB
- Available after Momentum: ~4.4GB ✅

---

*Last updated: 2026-03-05*
