# Momentum MGM

> **Civic AI Platform for Montgomery, Alabama**
> World Wide Vibes Hackathon — March 5–9, 2026

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Live](https://img.shields.io/badge/demo-mgm.styxcore.dev-blue)]()

---

## What is Momentum MGM?

Montgomery has no digital channel between citizens and city hall.

**Momentum MGM** is the same type of civic participation platform used by:

- **Barcelona** — Decidim live since 2016. 38 active participatory processes in 2024. 10,000+ citizen proposals shaped the city's strategic plan. Now used by 450+ organizations in 30+ countries.
- **Brazil** — Brasil Participativo: 1.5 million registered citizens, 7.5 million visits. 8,254 proposals during the 2024–2027 national plan process — 76% incorporated by government. Brazil is building an open-source AI system to process all incoming citizen input — launch planned for early 2026.
- **Taiwan** — vTaiwan + Pol.is: 28+ policy cases deliberated, 80% resulted in real government action. 4,000+ citizens produced Uber regulation consensus via Pol.is that became law.

**Montgomery doesn't have this. We built it — and added the AI layer that Brazil is still working toward.**

---

## Architecture

```
LAYER 1 — CITIZEN PLATFORM (Decidim 0.31.2, live at mgm.styxcore.dev)
  Citizens submit proposals, vote, comment across 10 civic categories
  Raspberry Pi 5 ARM64, native Ruby on Rails, Cloudflare tunnel

LAYER 2 — CIVIC DATA LAKE (real Montgomery open data, PostgreSQL + pgvector)

  civic_data.city_data — Montgomery ArcGIS Open Data (44,608 records total):
    fire_incidents          20,000
    code_violations         10,000
    building_permits         5,619
    housing_condition        5,561
    transit_stops            1,613
    food_safety              1,337
    environmental_nuisance     330
    education_facilities        97
    citizen_reports             16
    behavioral_centers          13
    opportunity_zones           12
    infrastructure_projects     10

  civic_data.census       — Census ACS 5-year estimates: 11,334 rows, 2012–2024, 71 tracts
  civic_data.businesses   — Yelp via Bright Data: 500 businesses
  civic_data.properties   — Zillow: 500 properties
  civic_data.embeddings   — pgvector (gemini-embedding-001, 3072d): 1,000 embeddings

LAYER 3 — MCP SERVER (12 tools, Python FastMCP, stdio transport)
  Connects Claude Desktop directly to Decidim + the data lake.
  City administrators query their city in plain language.
```

---

## The Governance Loop

```
DETECT     get_census_trend()         14 years of Census ACS OLS regression per neighborhood
           get_city_incidents()       12 ArcGIS sources, neighborhood-filtered, status breakdown

UNDERSTAND get_neighborhood_intelligence()  Census + Zillow + Yelp aggregated report
           semantic_civic_search()         pgvector cosine similarity across all civic data
           get_business_health()           Yelp closure rates, avg rating, foot traffic proxy

FIND       find_solutions()           Federal programs (HUD, CDBG, EPA, DOT) + comparable cities
           get_proposals()            What citizens are already asking for

ACT        recommend_action()         Concrete step + department + 311 service type
           classify_proposal()        AI classification into 10 civic categories
```

**Example query from city hall:**
> "What is happening in West Montgomery and what can we do about it?"

Claude calls `get_census_trend()` → 14 years of income, poverty, vacancy, unemployment, rent with slope per year and R² confidence. Then `get_city_incidents()` → code violations, fire incidents, housing conditions, food safety scores. Then `get_neighborhood_intelligence()` → Zillow prices, Yelp closures, business health. Then `find_solutions()` → matching federal grant programs (HUD Choice Neighborhoods, CDBG, EPA Brownfields) and comparable cities that solved similar problems. All real data. No hallucination.

---

## MCP Tools (12)

| Tool | Description |
|---|---|
| `get_proposals` | Citizen proposals from Decidim, filterable by category |
| `classify_proposal` | AI classification into 10 civic categories + 311 routing |
| `analyze_trends` | Proposal volume and top issues by votes |
| `recommend_action` | Concrete city administration action + department + 311 service type |
| `get_platform_summary` | Full Decidim platform snapshot |
| `get_montgomery_context` | Scraped Montgomery city data lookup |
| `get_neighborhood_intelligence` | Census + Zillow + Yelp multi-source aggregated report |
| `semantic_civic_search` | pgvector cosine similarity search across all civic data |
| `get_census_trend` | 14yr OLS regression per metric, projection to 2026, R² confidence |
| `get_city_incidents` | 12 ArcGIS sources: counts, status breakdown, date range |
| `get_business_health` | Yelp closure rate, avg rating, top categories by neighborhood |
| `find_solutions` | Federal programs + comparable cities + Montgomery-specific recommendations |

---

## Why No Existing Civic Platform Has This

Barcelona's Decidim doesn't have an AI admin bridge. Brazil's doesn't. Montreal's doesn't. The MCP server is what makes Momentum MGM a different category of product — not another Decidim deployment, but Decidim extended with a live civic intelligence layer that city administrators can query in plain language through Claude.

Brazil is building toward this. We shipped it.

---

## Tech Stack

| Component | Technology |
|---|---|
| Civic Platform | Decidim 0.31.2 (Ruby on Rails, native ARM64) |
| Database | PostgreSQL 15 + pgvector |
| AI — Classification | Gemini Flash via OpenRouter |
| AI — Solutions | Grok-4 via OpenRouter |
| AI — Embeddings | gemini-embedding-001 (3072d, Matryoshka, Google GenAI) |
| Data — City | Montgomery ArcGIS Open Data (no auth, REST pipeline) |
| Data — Census | US Census ACS API (free, 2012–2024) |
| Data — Private | Bright Data SDK (Zillow, Yelp) |
| MCP Server | Python 3.12, FastMCP, stdio transport |
| Infrastructure | Raspberry Pi 5 8GB, NVMe SSD, Nginx, Cloudflare tunnel |

---

## Repository Structure

```
momentum-mgm/
├── mcp-server/
│   ├── server.py          ← 12 MCP tools
│   ├── decidim_client.py  ← Decidim GraphQL client
│   └── requirements.txt
├── database/
│   └── 002_civic_data_lake.sql  ← civic_data schema + pgvector
├── seeder/
│   ├── lake.py            ← ArcGIS + Census + Bright Data pipeline
│   ├── siphon.py          ← Incremental refresh (systemd timer)
│   ├── seed.py            ← Proposal seeder (Grok-4)
│   └── requirements.txt
├── docs/
│   ├── architecture.md
│   ├── data_lake.md
│   └── bugs.md
└── systemd/               ← systemd services for automated data refresh
```

---

## Hackathon Timeline

| Day | Date | Milestone |
|---|---|---|
| 1 | Mar 5 | Decidim live at mgm.styxcore.dev |
| 2 | Mar 6 | Data lake: Census + ArcGIS (12 sources, 44,608 records) + Zillow + Yelp |
| 3 | Mar 7 | MCP server 12 tools complete |
| 4 | Mar 8 | End-to-end demo |
| 5 | Mar 9 | Submission |

---

## Team

Alexandre Breton (StyxKnight) — Architecture, AI, MCP

*Last updated: 2026-03-07*
