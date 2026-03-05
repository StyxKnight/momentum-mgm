# Backend Layer — MCP Server + Seeder

## Overview

The "backend" for Momentum MGM is two Python components:

1. **Seeder** — Bright Data scrapes Montgomery public data → AI generates proposals → Rails runner inserts into Decidim
2. **MCP Server** — Exposes 6 tools to Claude Desktop so administrators can interact with the platform in natural language

Decidim itself (Ruby on Rails) handles all civic platform logic: proposals, voting, user accounts, processes, assemblies. We don't touch that code.

> **Key divergence from original plan:** Seeder inserts via Rails runner, NOT GraphQL. Decidim 0.31 GraphQL is read-only. See DIV-001 in bugs.md.

---

## Component 1 — Bright Data Seeder

### Purpose
Populate the Decidim platform with real Montgomery civic data before launch so the demo platform isn't empty.

### Directory
```
seeder/
├── venv/              ← Python virtualenv (not committed)
├── requirements.txt
├── scrape.py          ← Bright Data → raw JSON files
├── seed.py            ← Grok-4-Fast generates proposals → Rails runner inserts
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
  → Calls Grok-4-Fast via OpenRouter to generate 6 proposals per category
  → Falls back to Gemini 2.5 Flash (google-genai SDK) if OpenRouter fails
  → Writes proposals to /tmp/momentum_proposals.json
  → Calls Rails runner to insert via ActiveRecord (bypasses GraphQL limitation)
```

### Key Decision: Rails Runner for Insertion (not GraphQL)
Decidim 0.31 GraphQL API is **read-only** by default — no admin mutations exposed.
Attempted `createProposal` mutation returns 0 available mutations on introspection. (See BUG-011)
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

### AI Generation — OpenRouter primary, Gemini fallback
Primary: `x-ai/grok-4-fast` via OpenRouter (fast, cost-effective)
Fallback: `gemini-2.5-flash` via Google Gemini (requires billing-enabled GCP project)

```python
from openai import OpenAI
from google import genai as google_genai

openrouter = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
gemini_direct = google_genai.Client(api_key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None

def generate_text(prompt: str) -> str:
    try:
        r = openrouter.chat.completions.create(
            model="x-ai/grok-4-fast",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
        )
        return r.choices[0].message.content
    except Exception as e:
        if gemini_direct:
            r = gemini_direct.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            return r.text
        raise
```

> **Note:** `google-generativeai` is fully deprecated as of 2026. Always use `google-genai`. (See BUG-013)

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
Note: We use 10 civic categories, NOT Reed's 5 priorities. Civic taxonomy is stable; priorities change with mayors. No `reed_priority` field. (See DIV-006 in bugs.md)

---

## Component 2 — MCP Server

### Purpose
Bridge between Claude Desktop and Decidim. City administrators talk to Claude; Claude calls these tools to read proposals, classify them, analyze trends, and generate recommendations.

### Directory
```
mcp-server/
├── requirements.txt
├── server.py          ← All 6 MCP tools (FastMCP, stdio transport)
└── decidim_client.py  ← GraphQL client (public reads only)
```

> **Note:** Original plan had a `tools/` subdirectory with multiple files. Actual implementation is flat — all tools in server.py. (See DIV-004 in bugs.md)

### Transport: stdio (NOT HTTP)
FastMCP uses stdio transport. Claude Desktop runs it as a subprocess:
```json
{
  "mcpServers": {
    "momentum-mgm": {
      "command": "python",
      "args": ["/path/to/mcp-server/server.py"]
    }
  }
}
```
No port is opened. No HTTP server. MCP runs as a child process of Claude Desktop.

### Tools Exposed to Claude (6 tools)

```python
@mcp.tool()
async def get_proposals(category: str = None, limit: int = 20) -> str:
    """Get citizen proposals from Decidim. Optional category filter."""

@mcp.tool()
async def classify_proposal(text: str) -> str:
    """Classify a proposal into one of 10 civic categories using AI."""

@mcp.tool()
async def analyze_trends() -> str:
    """Analyze platform trends — total count, top proposals by vote."""

@mcp.tool()
async def recommend_action(topic: str) -> str:
    """Generate concrete action recommendation for city administration on a topic."""

@mcp.tool()
async def get_platform_summary() -> str:
    """Full platform snapshot — totals, top issues, all categories."""

@mcp.tool()
async def get_montgomery_context(topic: str) -> str:
    """Query scraped Montgomery civic data (city pages, mayor priorities, 311 data)."""
```

> **Note:** `get_clusters` and `create_proposal` tools were in the original plan but do not exist. (See DIV-005 in bugs.md)

### GraphQL Client (decidim_client.py)
Used for all read operations. GraphQL API is public — no auth needed.
```python
DECIDIM_URL = os.getenv("DECIDIM_URL", "https://mgm.styxcore.dev")

async def graphql(query: str, variables: dict = None) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{DECIDIM_URL}/api",
            json={"query": query, "variables": variables or {}},
            timeout=30,
            follow_redirects=True,
        )
        return r.json()
```
> **Critical:** Always use the public URL (`https://mgm.styxcore.dev/api`), NEVER `localhost:3000/api`. Localhost returns 302 → `/system/` because org host doesn't match. (See BUG-016)

### AI in MCP Server
MCP classify/recommend tools use OpenRouter (Gemini Flash 1.5 via OpenRouter):
```python
r = await openrouter.chat.completions.create(
    model="google/gemini-flash-1.5",
    messages=[{"role": "user", "content": prompt}],
    max_tokens=250,
    response_format={"type": "json_object"},
)
```

---

## Requirements

### seeder/requirements.txt
```
brightdata-sdk>=2.2.0
openai>=1.0.0
google-genai>=1.0.0
python-dotenv>=1.0.0
requests>=2.31.0
```

### mcp-server/requirements.txt
```
mcp>=1.0.0
fastmcp>=0.1.0
httpx>=0.27.0
python-dotenv>=1.0.0
openai>=1.0.0
```

---

*Last updated: 2026-03-05*
