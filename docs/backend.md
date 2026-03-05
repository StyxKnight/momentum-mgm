# Backend Layer — MCP Server + Seeder

## Overview

The "backend" for Momentum MGM is two Python components:

1. **Seeder** — Bright Data scrapes Montgomery public data → Python seeds Decidim via GraphQL API
2. **MCP Server** — Exposes tools to Claude Desktop so administrators can interact with the platform in natural language

Decidim itself (Ruby on Rails) handles all civic platform logic: proposals, voting, user accounts, processes, assemblies. We don't touch that code.

---

## Component 1 — Bright Data Seeder

### Purpose
Populate the Decidim platform with real Montgomery civic data before launch so the demo platform isn't empty.

### Directory
```
seeder/
├── requirements.txt
├── .env.example
├── scrape.py          ← Bright Data → raw JSON files
├── seed.py            ← JSON → Decidim GraphQL API
├── categories.py      ← Reed priority mapping
└── data/
    └── scraped/       ← cached scrape output
```

### Data Sources (Bright Data targets)
```python
SOURCES = [
    {
        "url": "https://www.montgomeryal.gov/city-government/news",
        "type": "civic_news",
        "extract": ["title", "date", "summary"]
    },
    {
        "url": "https://www.montgomeryal.gov/residents/public-safety",
        "type": "public_safety",
        "extract": ["stats", "initiatives"]
    },
    {
        "url": "https://www.montgomeryal.gov/business",
        "type": "economic",
        "extract": ["programs", "incentives"]
    }
]
```

### Categories — Reed Priority Mapping
```python
CATEGORIES = {
    "public_safety": {
        "label": "Public Safety & Crime",
        "description": "Police, violence, repeat offenders, Aniah's Law",
        "reed_priority": 1,
        "color": "#EF4444",
        "icon": "🛡️",
    },
    "blight": {
        "label": "Blight & Neighborhood Revitalization",
        "description": "Abandoned buildings, Southern Boulevard, West Montgomery",
        "reed_priority": 2,
        "color": "#F97316",
        "icon": "🏚️",
    },
    "economy": {
        "label": "Economic Growth & Jobs",
        "description": "Small business, Meta investment, manufacturing, Access Montgomery",
        "reed_priority": 3,
        "color": "#22C55E",
        "icon": "💼",
    },
    "infrastructure": {
        "label": "Infrastructure & Smart City",
        "description": "Roads, transit, convention center, inland port",
        "reed_priority": 4,
        "color": "#3B82F6",
        "icon": "🏗️",
    },
    "services": {
        "label": "City Services & Access",
        "description": "Healthcare, housing, homelessness, opioids, digital access",
        "reed_priority": 5,
        "color": "#8B5CF6",
        "icon": "🏥",
    }
}
```

### Decidim GraphQL — Create Proposal
```python
# Auth: POST /api/sign_in → JWT token
# Then: POST /api with Authorization: Bearer <token>

CREATE_PROPOSAL_MUTATION = """
mutation CreateProposal($componentId: ID!, $title: String!, $body: String!) {
  createProposal(input: {
    componentId: $componentId
    title: { en: $title }
    body: { en: $body }
  }) {
    proposal {
      id
      title { en }
    }
    errors
  }
}
"""
```

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
