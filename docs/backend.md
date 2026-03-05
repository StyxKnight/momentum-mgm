# Backend Layer — MCP Server + Seeder

## Overview

The "backend" for Momentum MGM is two Python components:

1. **Seeder** — Bright Data scrapes Montgomery public data → Python seeds Decidim via GraphQL API
2. **MCP Server** — Exposes tools to Claude Desktop so administrators can interact with the platform in natural language

Decidim itself (Ruby on Rails) handles all civic platform logic: proposals, voting, user accounts, processes, assemblies. We don't touch that code.

---

## Component 1 — Bright Data Seeder

### Purpose
Populate the Decidim platform with real Montgomery civic data before launch so the demo platform isn't empty. Also powers ongoing data refresh as the platform grows.

### Directory
```
seeder/
├── venv/              ← Python virtualenv (not committed)
├── requirements.txt
├── scrape.py          ← Bright Data → raw JSON files
├── seed.py            ← Gemini Flash generates proposals → Rails runner inserts
└── data/
    └── scraped/       ← cached scrape output (committed)
        ├── city_pages.json
        ├── category_searches.json
        ├── mayor_priorities.json
        └── 311_data.json
```

### How It Works
```
scrape.py
  → Bright Data SDK (SyncBrightDataClient)
  → Scrapes: city pages, Google searches per category, mayor priorities, 311 data
  → Output: data/scraped/*.json

seed.py
  → Loads scraped JSON context
  → Calls Gemini 2.0 Flash (google-genai SDK) to generate 6 proposals per category
  → Writes proposals to /tmp/momentum_proposals.json
  → Calls Rails runner to insert via ActiveRecord (bypasses GraphQL limitation)
```

### Key Decision: Rails Runner for Insertion (not GraphQL)
Decidim 0.31 GraphQL API is **read-only** by default — no admin mutations exposed.
Attempted `createProposal` mutation returns 0 available mutations on introspection.
Solution: seed.py generates JSON → `/usr/local/bin/decidim-start.sh rails runner script.rb` inserts via ActiveRecord directly.
This is reliable, fast, and avoids any auth/permission complexity.

### Bright Data SDK Usage
```python
from brightdata import SyncBrightDataClient

with SyncBrightDataClient() as client:
    # Web search
    result = client.search.google(query="Montgomery Alabama ...", num_results=8)
    # Page scraping (bypasses anti-bot, CAPTCHAs, 403s)
    result = client.scrape_url("https://opendata.montgomeryal.gov/...")
```
Env var: `BRIGHTDATA_API_TOKEN`

### AI Generation — google-genai SDK (NOT google-generativeai)
`google-generativeai` is **fully deprecated** as of 2026. Always use `google-genai`.
```python
from google import genai
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
```

### 10 Civic Categories
```
infrastructure  → Infrastructure & Roads
environment     → Water, Utilities & Environment
housing         → Housing & Neighborhoods
public_safety   → Public Safety
transportation  → Transportation & Mobility
health          → Health & Social Services
education       → Education & Youth
economy         → Economy & Employment
parks_culture   → Parks, Culture & Recreation
governance      → Governance & Democracy
```
Note: No `reed_priority` field — categories are the source of truth, not a priority ranking.

---

## Component 2 — MCP Server

### Purpose
Bridge between Claude Desktop and Decidim. City administrators talk to Claude; Claude calls these tools to read proposals, classify them, analyze trends, and generate recommendations.

### Directory
```
mcp-server/
├── requirements.txt
├── .env.example
├── server.py          ← MCP server entry point
├── tools/
│   ├── proposals.py   ← get/create proposal tools
│   ├── classifier.py  ← Gemini Flash classification
│   ├── clusters.py    ← trend analysis
│   └── context.py     ← Montgomery civic data queries
└── decidim_client.py  ← GraphQL client wrapper
```

### Tools Exposed to Claude

```python
@mcp.tool()
async def get_proposals(
    category: str = None,
    district: str = None,
    limit: int = 20
) -> list[dict]:
    """
    Get citizen proposals from the Decidim platform.
    Filter by category (public_safety, blight, economy, infrastructure, services)
    or by district name.
    Returns proposals with title, body, vote count, and AI category.
    """

@mcp.tool()
async def classify_proposal(text: str) -> dict:
    """
    Classify a citizen proposal using Gemini Flash.
    Returns category, 1-sentence summary, confidence score, and top keywords.
    Aligned with Mayor Reed's 5 priority areas.
    """

@mcp.tool()
async def get_clusters() -> list[dict]:
    """
    Get thematic clusters of proposals grouped by AI.
    Shows what topics citizens are raising most, with proposal counts.
    """

@mcp.tool()
async def analyze_trends(category: str = None) -> dict:
    """
    Analyze proposal trends over time.
    Returns volume by category, trending topics, district breakdown.
    """

@mcp.tool()
async def get_montgomery_context(topic: str) -> dict:
    """
    Query scraped Montgomery civic data for context on a topic.
    E.g. topic='crime' returns relevant MPD stats and city initiatives.
    """

@mcp.tool()
async def recommend_action(cluster_id: int) -> dict:
    """
    Generate a concrete action recommendation for a proposal cluster.
    Cross-references with Reed's stated priorities and available civic programs.
    Returns: recommended action, relevant city department, urgency, next steps.
    """

@mcp.tool()
async def create_proposal(title: str, body: str, category: str) -> dict:
    """
    Create a new proposal in Decidim on behalf of the AI.
    Used to surface issues identified through civic data analysis.
    """
```

### AI Classifier — Prompt Template
```python
CLASSIFY_PROMPT = """
You are a civic AI assistant for Montgomery, Alabama.
Mayor Reed's stated priorities (in order):
1. Public Safety & Crime Reduction
2. Blight Removal & Neighborhood Revitalization
3. Economic Growth & Job Creation
4. Infrastructure & Smart City Development
5. City Services & Community Access

Classify this citizen proposal into ONE category:
- public_safety
- blight
- economy
- infrastructure
- services

Proposal: "{text}"

Respond in JSON only:
{{
    "category": "...",
    "summary": "One neutral sentence describing the proposal",
    "confidence": 0.0-1.0,
    "keywords": ["...", "...", "..."],
    "reed_alignment": "Brief note on how this aligns with Reed's priorities"
}}
"""
```

---

## Requirements

### seeder/requirements.txt
```
requests>=2.31.0
python-dotenv>=1.0.0
brightdata-sdk>=1.0.0   # or requests-based Bright Data calls
```

### mcp-server/requirements.txt
```
mcp>=1.0.0
httpx>=0.27.0
python-dotenv>=1.0.0
openai>=1.0.0           # OpenRouter is OpenAI-compatible
```

---

*Last updated: 2026-03-05*
