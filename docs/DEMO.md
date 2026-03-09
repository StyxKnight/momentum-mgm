# Momentum MGM — Live Demo Guide
**World Wide Vibes Hackathon | March 5–9, 2026**

---

## Connect in 30 Seconds

No setup. No local install. Works directly in **claude.ai** (web or mobile).

1. Go to **claude.ai** → Settings → Integrations (or "Connected apps")
2. Add a new MCP server with URL: `https://mcp.styxcore.dev/mcp`
3. 21 tools appear instantly in your Claude conversation

The platform, the data lake, and the AI are all live on a Raspberry Pi 5 in Montgomery, Alabama.

> Also compatible with Claude Desktop — add the URL under MCP servers in settings.

> **Live civic platform:** https://mgm.styxcore.dev
> **MCP endpoint:** https://mcp.styxcore.dev/mcp

---

## What You're Looking At

Montgomery, Alabama has a civic participation problem. Citizens report issues through 311 (reactive, siloed), but there's no system that connects community voice, open city data, and AI to drive strategic decisions.

Momentum MGM is that system. Three layers:

| Layer | What it is |
|---|---|
| **Decidim** at `mgm.styxcore.dev` | Citizens propose, vote, debate, answer surveys. Live. |
| **Data Lake** | ~60,600 ArcGIS records (16 sources) + 11,334 Census ACS + 500 Yelp + 500 Zillow + ~61K embeddings |
| **MCP Server** — 20 tools | The AI brain. Claude talks directly to the city. |

Precedent: Barcelona (10K proposals → strategic plan), Brazil (1.5M citizens, 76% integrated into national budget), Taiwan vTaiwan (80% → direct government action).

---

## Demo Scenario — The Full Civic Loop

Run these in order. Each step builds on the previous one.

---

### 1. What are citizens saying right now?

```
get_proposals()
```

Live proposals from Montgomery residents. Real people, real concerns — housing, infrastructure, public safety, environment. Sorted by vote count.

---

### 2. Find the silent zones — where data screams but no one is talking

```
detect_civic_gaps()
```

Cross-references ArcGIS incident density vs. Decidim proposal count by neighborhood.
Returns neighborhoods with the highest city data problems and the fewest citizen voices.
Pure SQL — no AI, no hallucination. Instant.

---

### 3. Deep dive on a neighborhood

```
civic_report("Centennial Hill")
```

One call aggregates:
- Census ACS 2012–2024 OLS regression (12 years of trend data, R² per metric)
- 16 ArcGIS sources: code violations, building permits, housing condition, fire incidents, food safety, environmental nuisance, business licenses, transit, parks, zoning, and more
- Yelp business health (closure rate, avg rating, top categories)
- Zillow housing market (avg price, days on market)
- ADI / SVI / EJI composite deprivation scores vs. all 71 Montgomery census tracts
- Citizen survey signals — what residents said they prioritized in platform surveys

**Real output:**
```json
{
  "overall_severity": "critical",
  "severity_rationale": "ADI 0.938 — worse than 94% of Montgomery neighborhoods",
  "findings": [
    { "category": "housing", "finding": "Vacant units at 26.1% of housing stock — highest in city", "trend": "declining" },
    { "category": "economy", "finding": "Median income $31,200 — 51% below city median of $64,249", "trend": "stable" }
  ]
}
```

No hallucinations. Every number verified against the database before the AI writes a single word.

---

### 4. Find concrete solutions — federal programs + global best practices

```
find_solutions("high vacancy rate and code violations", "Centennial Hill")
```

Three parallel Brave Search queries feed Gemini 2.5 Flash:
- Federal programs (HUD, EPA, USDA, Treasury)
- Global comparable cities (what worked in Louisville, Detroit, Leipzig)
- Montgomery-specific context

Real federal URLs. Real cities. Real Montgomery statistics embedded in every recommendation.

---

### 5. Classify a citizen proposal and recommend an action

```
classify_proposal("We need better street lighting on Mobile Road — it's dangerous at night")
```

Maps citizen voice to 10 civic categories. Determines 311 actionability. No hallucination — pure logic + embeddings.

```
recommend_action("We need better street lighting on Mobile Road — it's dangerous at night")
```

Returns department routing + priority score + next step.

---

### 6. Close the civic loop — AI responds directly on the platform

Take any proposal ID from `get_proposals()` and run:

```
post_ai_response("112")
```

Full pipeline in one call:
1. Fetches the proposal + existing citizen comments
2. Classifies it → detects category + neighborhood
3. Pulls `civic_report()` for that neighborhood — real data
4. Gets next public meeting on topic
5. Generates a 3–4 sentence comment (Gemini 2.5 Flash, warm tone, no jargon)
6. Posts it on Decidim as Momentum AI via authenticated GraphQL

**Then visit mgm.styxcore.dev and see the comment appear on the proposal. Live.**

---

### 7. Same thing for debates

```
post_debate_summary("10")
```

Debate #10 is "Protecting the Alabama River Ecosystem."

If no citizen comments yet → AI posts an opening brief with real environmental data on both sides.
If comments exist → AI posts a neutral synthesis: what supporters argue, what opponents say, what the data shows.

---

### 8. Export to Google Workspace

```
export_to_sheet("West Side")
```
All civic data for West Side → Google Sheets. Shareable link returned.

```
create_report_doc("West Side")
```
Full executive briefing → Google Doc. Prose format, readable by city officials. Shareable link returned.

```
sync_gcal()
```
All Decidim meetings → Google Calendar. Deduplication handled.

---

### 9. Understand what citizens want — survey results

```
summarize_comments("124")
```

Proposal #124 is the most contested: "Halt the Alabama River Corridor Project."
7 supporters, 7 opponents, 6 mixed — sentiment analysis across all comments.

---

### 10. City-wide neighborhood ranking

```
analyze_neighborhood("list")
```

Top 5 most deprived neighborhoods by ADI score — z-score normalized across all 71 census tracts. Methodology: UW Madison Neighborhood Atlas + CDC/ATSDR SVI + EPA EJI.

---

### 11. Participatory budgeting — who gets funded?

```
get_budget_results()
```

Montgomery Federal Community Development Allocation 2026: $2,698,000 available, 10 projects submitted totaling $4,148,000 — $1,450,000 over-subscribed.

20 simulated citizens voted based on their civic concern profiles (housing, economy, health, etc.). In real deployment the seed data is purged — real citizens vote directly on mgm.styxcore.dev. `get_budget_results` reads whatever votes exist in the DB. The greedy algorithm allocates by vote count descending within the budget envelope.

Every project is grounded in real ArcGIS incident counts:
- North Montgomery / Chisholm: 2,118 housing condition violations — highest in the city
- Cottage Hill: 1,581 housing condition violations
- Downtown: 1,716 code violations

No invention. No politics. Data-driven allocation — the same logic Barcelona uses for its participatory budget.

---

## What Makes This Different

| Claim | Proof |
|---|---|
| Real data, not fake | ~60,600 city records from 16 ArcGIS sources, live |
| No hallucinations | Every AI output grounded in DB-verified numbers |
| Full civic loop | Citizen proposes → AI reads city data → AI responds on platform |
| Live platform | Real proposals, real debates, real survey results |
| Methodology | ADI (UW Madison/HRSA) + SVI (CDC/ATSDR) + EJI (EPA) — peer reviewed |
| Reproducible | Every judge can run every tool right now, same results |

---

## Architecture

```
Claude Desktop / Claude Mobile
    ↕ MCP HTTP (mcp.styxcore.dev/mcp)
FastMCP Server — 21 tools (Python, Raspberry Pi 5 ARM64)
    ↕
┌────────────────────────────────────────────┐
│ PostgreSQL — momentum DB                   │
│   civic_data.city_data    (~60,600 rows)   │
│   civic_data.census        (11,334 rows)   │
│   civic_data.businesses      (500 rows)    │
│   civic_data.properties      (500 rows)    │
│   civic_data.embeddings    (~61,000 rows)  │
└────────────────────────────────────────────┘
    ↕
Decidim 0.31.2 (mgm.styxcore.dev) — GraphQL API
    ↕
Gemini 2.5 Flash (primary) · Grok-4 via OpenRouter (fallback)
Brave Search API (live web for find_solutions)
Google Workspace API (Sheets · Docs · Calendar)
```

---

## All 20 Tools

| # | Tool | What it does |
|---|---|---|
| 1 | `get_proposals` | Live citizen proposals from Decidim |
| 2 | `classify_proposal` | Maps text to 10 civic categories + 311 routing |
| 3 | `semantic_civic_search` | pgvector cosine similarity across ~61K embeddings |
| 4 | `get_census_trend` | OLS regression 14 years Census ACS |
| 5 | `get_city_incidents` | 19 ArcGIS sources, count + status |
| 6 | `get_business_health` | Yelp closure rate, avg rating |
| 7 | `find_solutions` | Federal programs + global best practices + local |
| 8 | `analyze_neighborhood` | ADI / SVI / EJI composite scores |
| 9 | `civic_report` | Full AI report — all sources, Gemini 2.5 Flash |
| 10 | `post_ai_response` | AI comment on citizen proposal (WRITE) |
| 11 | `get_meetings` | Public meetings from Decidim |
| 12 | `summarize_comments` | Sentiment analysis on proposal comments |
| 13 | `export_to_sheet` | Civic data → Google Sheets |
| 14 | `create_report_doc` | Executive briefing → Google Doc |
| 15 | `sync_gcal` | Decidim meetings → Google Calendar |
| 16 | `create_report_slides` | Civic intelligence report → Google Slides |
| 17 | `create_action_tasks` | Priority actions → Google Tasks |
| 18 | `detect_civic_gaps` | Silent zones — high incidents, zero citizen voice |
| 19 | `post_debate_summary` | AI opening brief / synthesis on debate thread (WRITE) |
| 20 | `get_budget_results` | Participatory budget vote results — funded vs rejected |

---

*Built in 5 days on a Raspberry Pi 5 (8GB RAM, NVMe SSD) running ARM64 Linux.*
*Montgomery, Alabama — population 199,518.*
