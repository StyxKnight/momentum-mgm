# Momentum MGM — Demo Script
**World Wide Vibes Hackathon | March 5-9, 2026**

---

## What This Is

Montgomery, Alabama has a civic participation problem. Citizens report issues through 311 (reactive), but there's no system that connects community voice, open data, and AI to drive strategic decisions.

Momentum MGM is that system. Three layers:

- **Layer 1 — Decidim** (`mgm.styxcore.dev`): Citizens propose, vote, comment. Live platform.
- **Layer 2 — Data Lake**: 44,608 ArcGIS records + 11,334 Census ACS + 500 Yelp + 500 Zillow. Real Montgomery data.
- **Layer 3 — MCP Server**: 14 AI tools that connect everything. Claude talks directly to the city.

Precedents: Barcelona (10K proposals → strategic plan), Brazil (1.5M citizens, 76% proposals integrated into national budget), Taiwan vTaiwan (80% → direct government action).

---

## Demo Sequence

### Step 1 — What are citizens saying?

```
get_proposals()
```

Live proposals from Montgomery residents on the Decidim platform. Real people, real concerns.

```
analyze_trends()
```

What topics are rising? What has the most votes?

---

### Step 2 — Classify a citizen proposal

Take any proposal text from Step 1 and run:

```
classify_proposal("We need better street lighting on Mobile Road —
  it's dangerous at night and crime is going up")
```

Expected output:
- category: `public_safety` or `infrastructure`
- confidence: ~0.92
- 311_actionable: true
- 311_note: "Street lighting service request to Public Works"

The AI maps citizen voice to the 10 official civic categories and determines if it generates a 311 action.

---

### Step 3 — Deep dive on a neighborhood

```
civic_report("West Side")
```

This single call aggregates:
- Census ACS 2012-2024 OLS regression (13 years of trend data)
- ArcGIS incidents: code violations, building permits, housing condition, fire incidents, food safety, environmental nuisance
- Yelp business health (closure rate, avg rating)
- ADI / SVI / EJI composite deprivation scores vs. all 71 Montgomery census tracts

**Real output (West Side):**
```json
{
  "overall_severity": "high",
  "severity_rationale": "ADI 0.562, EJI 0.625 — more deprived than 56-62% of Montgomery neighborhoods",
  "findings": [
    { "category": "public_safety", "finding": "1,774 code violations — top factor driving ADI and EJI scores", "trend": "unknown" },
    { "category": "housing", "finding": "Vacant units up from 201 (2012) to 216 (2024), moderate confidence R²=0.581", "trend": "declining" },
    { "category": "housing", "finding": "Median rent +48% since 2012 ($678 → $1,003), R²=0.946", "trend": "improving" },
    { "category": "economy", "finding": "Median income +58% since 2012 ($32K → $51K), R²=0.911", "trend": "improving" }
  ]
}
```

No hallucinations. Every number is verified against the database before the AI writes a single word.

---

### Step 4 — Find concrete solutions

```
find_solutions("high code violations and rising vacancy rate", "West Side")
```

Three parallel Brave Search queries (federal programs, global best practices, Montgomery-specific) feed a Gemini 2.5 Flash prompt grounded in real Census statistics.

**Real output:**
```json
{
  "federal_programs": [
    {
      "name": "Community Development Block Grant",
      "agency": "HUD",
      "eligibility": "Low-to-moderate income areas — West Side qualifies",
      "source_url": "https://www.hud.gov/program_offices/comm_planning/cdbg"
    }
  ],
  "comparable_cities": [
    { "city": "Louisville", "approach": "Strategic reevaluation of code enforcement targeting historic vacancy corridors", "lesson": "Compliance-first model outperforms fine-first in reducing long-term vacancy" },
    { "city": "Lancaster, Pennsylvania", "approach": "Code enforcement tied to property value recovery program", "lesson": "Enforcement + assistance = increased property values and decreased crime" }
  ],
  "montgomery_recommendations": [
    "Direct CDBG funds to West Side property rehabilitation — 216 vacant units and 1,774 violations create direct eligibility",
    "Shift to proactive systematic inspection rather than complaint-based — data shows violation density, not random distribution",
    "Compliance-focused model: assist owners first, fine second — proven in Louisville and Lancaster"
  ],
  "urgency": "high",
  "estimated_timeline": "2-3 years to see impact"
}
```

Real federal URLs. Real comparable cities from live web search. Real Montgomery statistics embedded in every recommendation.

---

### Step 5 — Semantic search across 45K records

```
semantic_civic_search("abandoned buildings near schools", "West Side")
```

pgvector cosine similarity across 45,600+ embeddings (properties + businesses + ArcGIS city data).
Finds conceptually related records, not just keyword matches.

---

### Step 6 — Neighborhood deprivation scores

```
analyze_neighborhood("list")
```

Returns the 5 most deprived neighborhoods in Montgomery by ADI score.
Z-score normalization + percentile rank computed across all 71 census tracts.

```
analyze_neighborhood("Centennial Hill", "all")
```

Real output: ADI 0.938 = worse than 94% of Montgomery neighborhoods.

---

## Why This Matters to Judges

| Dimension | Momentum MGM |
|-----------|-------------|
| Data volume | 57K+ records across 5 sources |
| AI architecture | MCP Server — Claude talks directly to city data |
| Anti-hallucination | All numbers DB-verified before AI prompt |
| Civic precedent | Barcelona, Brazil, Taiwan model |
| Live platform | Real citizens at mgm.styxcore.dev |
| Reproducibility | Every finding citable to source + methodology |

The methodology (ADI/SVI/EJI) is peer-reviewed: UW Madison, CDC/ATSDR, EPA. Not invented for this hackathon.

---

## Technical Stack

```
Claude Desktop
    ↕ MCP (stdio)
momentum-mgm MCP Server (Python, FastMCP)
    ↕
┌─────────────────────────────────────────┐
│ PostgreSQL momentum DB                  │
│   civic_data.city_data    (44,608)      │
│   civic_data.census       (11,334)      │
│   civic_data.businesses   (500)         │
│   civic_data.properties   (500)         │
│   civic_data.embeddings   (45,600+)     │
└─────────────────────────────────────────┘
    ↕
Decidim 0.31.2 (mgm.styxcore.dev) — GraphQL API
    ↕
Gemini 2.5 Flash (primary) / Grok-4 via OpenRouter (fallback)
Brave Search API (live web for find_solutions)
```

---

## Pre-Demo Checklist

- [ ] Decidim live at mgm.styxcore.dev
- [ ] MCP server running: `cd mcp-server && source venv/bin/activate && python server.py`
- [ ] At least 3 proposals on the platform
- [ ] BRIGHT_DATA_API_KEY revoked before submission
- [ ] `.env` not committed to repo
