# Momentum MGM

> **Civic AI Platform for Montgomery, Alabama**
> World Wide Vibes Hackathon — March 5–9, 2026

[![Live](https://img.shields.io/badge/platform-mgm.styxcore.dev-blue)](https://mgm.styxcore.dev)
[![MCP](https://img.shields.io/badge/MCP-mcp.styxcore.dev%2Fmcp-green)](https://mcp.styxcore.dev/mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What is Momentum MGM?

Montgomery has no digital channel between citizens and city hall.

**Momentum MGM** is the same civic participation platform used by:

- **Barcelona** — Decidim live since 2016. 10,000+ citizen proposals shaped the city's strategic plan. Now used by 450+ organizations in 30+ countries.
- **Brazil** — Brasil Participativo: 1.5M registered citizens, 8,254 proposals during the 2024–2027 national plan — 76% incorporated by government. Brazil is building an AI system to process citizen input — launch planned for early 2026.
- **Taiwan** — vTaiwan + Pol.is: 28+ policy cases deliberated, 80% resulted in real government action.

**Montgomery doesn't have this. We built it — and added the AI layer that Brazil is still working toward.**

---

## Architecture

```
LAYER 1 — CITIZEN PLATFORM (Decidim 0.31.2, live at mgm.styxcore.dev)
  Citizens submit proposals, vote, comment across 10 civic categories
  Simulated civic society: 20 citizens, 40 proposals, 60 comments, 12 public meetings
  Raspberry Pi 5 ARM64, native Ruby on Rails, Cloudflare tunnel

  NOTE: Seeded citizens (20 characters) are SIMULATION ONLY — demo for judges.
  In real deployment they are purged. AI tools remain active. The AI never
  impersonates a citizen — always signs as "Momentum AI".

LAYER 2 — CIVIC DATA LAKE (real Montgomery open data, PostgreSQL + pgvector)

  civic_data.city_data — Montgomery ArcGIS Open Data (60,609 records, 19 sources):
    fire_incidents          ~20,000     business_licenses         12,751
    code_violations         ~10,000     zoning_decisions           2,005
    building_permits          5,619     city_owned_property          681
    housing_condition         5,561     historic_markers             319
    transit_stops             1,613     parks_recreation              97
    food_safety               1,337     community_centers             24
    environmental_nuisance      330     education_facility           114
    education_facilities         97     citizen_reports               16
    behavioral_centers           13     opportunity_zones             12
    infrastructure_projects      10

  civic_data.census       — Census ACS 5-year estimates: 11,334 rows, 2012–2024, 71 tracts
  civic_data.businesses   — Yelp via Bright Data: 500 businesses
  civic_data.properties   — Zillow: 500 properties
  civic_data.embeddings   — pgvector (gemini-embedding-001, 3072d): ~61,000 embeddings

LAYER 3 — MCP SERVER (19 tools, Python FastMCP)
  Connects Claude directly to Decidim + the data lake + Google Workspace.
  Available at: https://mcp.styxcore.dev/mcp
  City administrators query their city in plain language — from any device.
```

---

## The Governance Loop

```
CITIZEN submits proposal on mgm.styxcore.dev
    ↓
DETECT     get_census_trend()          14yr OLS regression per metric, R² confidence
           get_city_incidents()        19 ArcGIS sources, neighborhood-filtered
           get_business_health()       Yelp closure rates, avg rating
           get_job_market()            Unemployment, income, education, poverty vs city avg

UNDERSTAND analyze_neighborhood()     ADI + SVI + EJI composite deprivation scores
           detect_civic_gaps()        Silent zones — high incidents, zero citizen voice
           semantic_civic_search()    pgvector cosine similarity across all civic data
           summarize_comments()       Sentiment + theme extraction on proposal comments

REPORT     civic_report()             Full AI report — RAG + Gemini 2.5 Flash + CoT
           find_solutions()           Federal programs + comparable cities + concrete actions

ACT        post_ai_response()         Civic loop closed: neighborhood report → AI comment on Decidim
           export_to_sheet()          Neighborhood data → Google Sheets (live)
           create_report_doc()        Full report → Google Doc (shareable)
           sync_gcal()                Public meetings → Google Calendar
```

**Example:** City administrator asks Claude: *"What is happening in West Montgomery and what should we do?"*

Claude calls `get_census_trend()` → 14 years of income, poverty, vacancy. Then `get_city_incidents()` → code violations, fire incidents by neighborhood. Then `analyze_neighborhood()` → ADI/SVI/EJI scores vs 71 Montgomery tracts. Then `find_solutions()` → real HUD CDBG programs with deadlines and dollar amounts. Then `create_report_doc()` → formatted Google Doc lands in city hall Drive, shared and ready.

All real data. No hallucination. Grounded in actual Montgomery statistics.

---

## MCP Tools (20)

### Decidim Layer
| Tool | Description |
|---|---|
| `get_proposals` | Live citizen proposals from Decidim. Filter by category: public_safety, housing, economy, infrastructure, environment, health, education, transportation. Returns title, body, vote count. |
| `classify_proposal` | Gemini 2.5 Flash classifies any text into 10 civic categories. Returns category, confidence, keywords, and whether a 311 ticket should be opened. |
| `get_meetings` | All public meetings and hearings from Decidim — city council sessions, participatory process assemblies, public consultations. `upcoming_only=True` filters to future meetings. |
| `summarize_comments` | Fetches all citizen comments on a proposal. Returns AI summary: sentiment, support_level, key themes, main concerns, consensus points. |
| `post_ai_response` | **WRITE** — Full civic loop: fetches proposal + comments → classifies → pulls civic_report for the neighborhood → gets next public meeting → generates a grounded 3–4 sentence comment → posts on Decidim as Momentum AI. |
| `post_debate_summary` | **WRITE** — AI reads a debate thread. If empty: posts an opening brief with real city data on both sides. If comments exist: posts a neutral synthesis of pro/contra positions + data layer. Works on both participatory processes and assemblies. |

### Data Lake Layer
| Tool | Description |
|---|---|
| `get_census_trend` | OLS linear regression on Census ACS 2012–2024 for 5 metrics: median_income, poverty_below, housing_vacant, unemployed, median_rent. Returns slope, current value, 2026 projection, R² per metric. R² < 0.5 flagged low_confidence. |
| `get_city_incidents` | Raw ArcGIS counts for one source at a time across 16 city datasets. `source='list'` returns all sources with totals. Filterable by neighborhood. No AI — pure SQL. |
| `get_business_health` | Yelp data: total businesses, closed count, avg rating, avg review count (foot traffic proxy), top 5 categories. Closure rate > 15% = commercial distress (LISC standard). |
| `semantic_civic_search` | pgvector cosine similarity across ~61K embeddings (gemini-embedding-001, 3072d). Finds conceptually related properties, businesses, and city records. Example: "abandoned buildings near schools". |

### Analysis Layer
| Tool | Description |
|---|---|
| `analyze_neighborhood` | Computes ADI (UW Madison/HRSA), SVI (CDC/ATSDR), EJI (EPA) for any Montgomery neighborhood. Z-score normalized + percentile ranked against all 71 census tracts. Score 0–1, higher = worse. `neighborhood='list'` returns top 5 most deprived. |
| `detect_civic_gaps` | Finds silent zones — neighborhoods with high ArcGIS incident density but zero citizen proposals on Decidim. gap_score = incident_load / max(1, proposals). Pure SQL, no AI. |
| `get_job_market` | Census ACS workforce indicators for any Montgomery neighborhood: unemployment rate, median household income, education attainment (bachelor's+), poverty rate — all compared vs city-wide averages. Pure SQL, instant. Covers all 10 civic categories including workforce/economy. |

### Report + Solutions Layer
| Tool | Description |
|---|---|
| `civic_report` | Full civic intelligence report. Aggregates Census OLS + 19 ArcGIS sources + Yelp + Zillow + ADI/SVI/EJI scores + workforce indicators (Census ACS) + citizen survey signals → Gemini 2.5 Flash (temp 0.1) with Jinja2 RAG prompt + Chain of Thought. Covers all 10 civic categories: housing, economy, environment, public_safety, health, infrastructure, workforce, transportation, education, parks_culture, governance. All numbers DB-verified before AI writes a word. 20–40s latency. |
| `find_solutions` | 3 parallel Brave Search queries (federal programs, global best practices, Montgomery-specific) + real Census stats → Gemini 2.5 Flash (temp 0.4). Returns active HUD/EPA/DOT grant programs with real URLs, comparable city case studies, concrete local recommendations. 30–60s latency. |

### Google Workspace Layer
| Tool | Description |
|---|---|
| `export_to_sheet` | Census trends + ArcGIS incidents + business health + ADI/SVI/EJI scores → Google Sheets. Creates or reuses "Momentum MGM — Civic Intelligence" spreadsheet. Returns shareable link. |
| `create_report_doc` | Runs civic_report + find_solutions → Gemini rewrites as executive prose → Google Doc. Ready for city hall. Returns shareable link. |
| `sync_gcal` | Syncs all Decidim public meetings to Google Calendar with deduplication. Creates "Montgomery Civic — Public Meetings" calendar if needed. |
| `create_report_slides` | Civic intelligence report → Google Slides presentation. |
| `create_action_tasks` | Priority actions from civic analysis → Google Tasks. |

### Participatory Budgeting Layer
| Tool | Description |
|---|---|
| `get_budget_results` | Participatory budget voting results. Vote count per project, funded vs rejected (greedy by votes within total budget), voter turnout, funding gap. `budget_id` optional — defaults to most recent active budget. Pure SQL, instant. Reusable every budget cycle. |

---

## Connect to Claude

The MCP server is live and public. Add it as a connector in Claude (web or mobile):

```
https://mcp.styxcore.dev/mcp
```

No authentication required. All 21 tools immediately available.

---

## Why No Existing Civic Platform Has This

Barcelona's Decidim doesn't have an AI admin bridge. Brazil's doesn't. Montreal's doesn't.

The MCP server is what makes Momentum MGM a different category of product — not another Decidim deployment, but Decidim extended with a live civic intelligence layer connected to real city data, queryable in plain language through Claude from any device, with outputs that flow directly into Google Workspace tools city hall already uses.

Brazil is building toward this. We shipped it.

---

## Tech Stack

| Component | Technology |
|---|---|
| Civic Platform | Decidim 0.31.2 (Ruby on Rails, native ARM64) |
| Database | PostgreSQL 15 + pgvector |
| AI — Primary | Gemini 2.5 Flash (Google GenAI direct API) |
| AI — Fallback | Grok-4 via OpenRouter |
| AI — Embeddings | gemini-embedding-001 (3072d, Matryoshka) |
| Data — City | Montgomery ArcGIS Open Data (19 sources, REST pipeline) |
| Data — Census | US Census ACS API (free, 2012–2024, 71 tracts) |
| Data — Private | Bright Data SDK (Zillow, Yelp) |
| MCP Server | Python 3.12, FastMCP, stdio + streamable-HTTP transports |
| Google Workspace | Sheets + Docs + Calendar + Drive (OAuth2) |
| Infrastructure | Raspberry Pi 5 8GB, NVMe SSD, Cloudflare tunnel |

---

## Repository Structure

```
momentum-mgm/
├── mcp-server/
│   ├── server.py              ← 19 MCP tools
│   ├── workspace_client.py    ← Google Workspace (Sheets, Docs, Calendar, Drive)
│   ├── decidim_client.py      ← Decidim GraphQL client (read + write, JWT auth)
│   ├── authorize_google.py    ← One-time OAuth2 flow
│   ├── prompts/               ← Jinja2 templates (base.j2, civic_report.j2, find_solutions.j2)
│   └── requirements.txt
├── database/
│   └── 002_civic_data_lake.sql  ← civic_data schema + pgvector
├── seeder/
│   ├── lake.py                ← ArcGIS + Census + Bright Data pipeline
│   ├── siphon.py              ← Incremental data refresh (systemd timer)
│   ├── seed_society.py        ← Civic society simulation (20 citizens, 40 proposals)
│   └── requirements.txt
├── docs/
│   ├── analysis_methodology.md  ← ADI, SVI, EJI methodology
│   ├── google_workspace_plan.md
│   └── bugs.md
└── systemd/                   ← systemd services for automated data refresh
```

---

## Hackathon Timeline

| Day | Date | Milestone |
|---|---|---|
| 1 | Mar 5 | Decidim live at mgm.styxcore.dev |
| 2 | Mar 6 | Data lake: 60K records ArcGIS + Census + Zillow + Yelp + 61K embeddings |
| 3 | Mar 7 | MCP server 15 tools, civic loop closed, simulated civic society |
| 4 | Mar 8 | Google Workspace, MCP HTTP live at mcp.styxcore.dev/mcp, tool audit, neighborhood fuzzy matching, detect_civic_gaps (tool 18), next_steps guidance in all tools |
| 5 | Mar 9 | Submission |

---

## Team

Alexandre Breton (StyxKnight) — Architecture, AI, MCP, Civic Platform

*Last updated: 2026-03-08 (Day 4)*
