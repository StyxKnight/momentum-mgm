"""
Momentum MGM — MCP Server
Bridges Claude Desktop ↔ Decidim civic platform
"""
import os
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from openai import AsyncOpenAI
from decidim_client import graphql

load_dotenv()

SCRAPED_DATA_DIR = Path(__file__).parent.parent / "seeder" / "data" / "scraped"

mcp = FastMCP("momentum-mgm")
openrouter = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

CATEGORIES = {
    "infrastructure":   {"label": "Infrastructure & Roads",           "color": "#3B82F6", "icon": "🏗️",  "311_link": True},
    "environment":      {"label": "Water, Utilities & Environment",   "color": "#22C55E", "icon": "🌿",  "311_link": True},
    "housing":          {"label": "Housing & Neighborhoods",          "color": "#F97316", "icon": "🏘️",  "311_link": True},
    "public_safety":    {"label": "Public Safety",                    "color": "#EF4444", "icon": "🛡️",  "311_link": True},
    "transportation":   {"label": "Transportation & Mobility",        "color": "#6366F1", "icon": "🚌",  "311_link": True},
    "health":           {"label": "Health & Social Services",         "color": "#EC4899", "icon": "🏥",  "311_link": False},
    "education":        {"label": "Education & Youth",                "color": "#F59E0B", "icon": "🎓",  "311_link": False},
    "economy":          {"label": "Economy & Employment",             "color": "#10B981", "icon": "💼",  "311_link": False},
    "parks_culture":    {"label": "Parks, Culture & Recreation",      "color": "#84CC16", "icon": "🌳",  "311_link": True},
    "governance":       {"label": "Governance & Democracy",           "color": "#8B5CF6", "icon": "🗳️",  "311_link": False},
}
# 311_link = True → this category directly maps to Montgomery 311 service requests
# 311_link = False → civic participation / policy proposals, feeds context to 311


# ── TOOL 1 ─────────────────────────────────────────────────────────────────────
@mcp.tool()
async def get_proposals(category: str = None, limit: int = 20) -> str:
    """
    Get citizen proposals from the Momentum MGM platform.
    Optionally filter by category: public_safety, blight, economy, infrastructure, services.
    Returns proposals with title, body, vote count.
    """
    query = """
    query($limit: Int!) {
      components(filter: { type: "Proposals" }) {
        id
        name { en }
        ... on Proposals {
          proposals(first: $limit) {
            nodes {
              id
              title { en }
              body { en }
              totalVotes
              publishedAt
            }
          }
        }
      }
    }
    """
    data = await graphql(query, {"limit": limit})
    proposals = []
    for comp in (data.get("data", {}).get("components") or []):
        nodes = (comp.get("proposals") or {}).get("nodes") or []
        for p in nodes:
            proposals.append({
                "id": p["id"],
                "title": p["title"]["en"],
                "body": (p["body"]["en"] or "")[:300],
                "votes": p.get("totalVotes", 0),
            })
    return json.dumps(proposals, ensure_ascii=False, indent=2)


# ── TOOL 2 ─────────────────────────────────────────────────────────────────────
@mcp.tool()
async def classify_proposal(text: str) -> str:
    """
    Classify a citizen proposal using AI (Gemini Flash).
    Returns category (one of 10 civic categories), summary, confidence, keywords.
    """
    prompt = f"""You are a civic AI assistant for Montgomery, Alabama.

Momentum MGM is a civic participation platform — NOT a replacement for 311, but its strategic complement.
311 = reactive (report broken things). Momentum MGM = proactive (propose, vote, build together).
Proposals on this platform feed context and community voice to city decision-makers.

Classify this proposal into ONE of these official civic categories:
- infrastructure   → Infrastructure & Roads (roads, bridges, sidewalks, lighting)
- environment      → Water, Utilities & Environment (water, sewers, flooding, air quality)
- housing          → Housing & Neighborhoods (blight, abandoned buildings, code enforcement)
- public_safety    → Public Safety (police, fire, crime prevention)
- transportation   → Transportation & Mobility (transit, parking, bike lanes, accessibility)
- health           → Health & Social Services (public health, homelessness, mental health)
- education        → Education & Youth (schools, youth programs, libraries)
- economy          → Economy & Employment (small business, jobs, investment)
- parks_culture    → Parks, Culture & Recreation (parks, arts, sports, community spaces)
- governance       → Governance & Democracy (civic processes, budget participation, transparency)

Proposal: "{text}"

Respond in JSON only:
{{
  "category": "...",
  "summary": "One neutral sentence describing the proposal",
  "confidence": 0.0,
  "keywords": ["...", "...", "..."],
  "311_actionable": true,
  "311_note": "If 311_actionable is true, what 311 service request this could generate. Otherwise null."
}}"""

    r = await openrouter.chat.completions.create(
        model="google/gemini-flash-1.5",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=250,
        response_format={"type": "json_object"},
    )
    return r.choices[0].message.content


# ── TOOL 3 ─────────────────────────────────────────────────────────────────────
@mcp.tool()
async def analyze_trends() -> str:
    """
    Analyze current proposal trends on the platform.
    Returns total counts, top topics, most voted proposals, and priority alignment.
    """
    query = """
    query {
      components(filter: { type: "Proposals" }) {
        ... on Proposals {
          proposals(first: 100) {
            nodes {
              id
              title { en }
              totalVotes
            }
          }
        }
      }
    }
    """
    data = await graphql(query)
    proposals = []
    for comp in (data.get("data", {}).get("components") or []):
        nodes = (comp.get("proposals") or {}).get("nodes") or []
        proposals.extend(nodes)

    top = sorted(proposals, key=lambda p: p.get("totalVotes", 0), reverse=True)[:5]
    result = {
        "total_proposals": len(proposals),
        "top_by_votes": [
            {"title": p["title"]["en"], "votes": p.get("totalVotes", 0)}
            for p in top
        ],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── TOOL 4 ─────────────────────────────────────────────────────────────────────
@mcp.tool()
async def recommend_action(topic: str) -> str:
    """
    Generate a concrete action recommendation for city administration on a given civic topic.
    Cross-references with Mayor Reed's priorities and Montgomery's available programs.
    Example topic: 'street lighting in West Montgomery', 'blight on Southern Blvd'
    """
    prompt = f"""You are advising the city administration of Montgomery, Alabama.

Topic raised by citizens on the Momentum MGM civic platform: "{topic}"

Montgomery has a 311 system for reactive service requests. Momentum MGM captures proactive civic proposals.
Your role: advise how city hall should respond, and whether this should also generate a 311 action.

Provide a concrete action recommendation in JSON:
{{
  "urgency": "high|medium|low",
  "department": "Which city department to involve",
  "recommended_action": "Specific, actionable step for city administration",
  "generates_311": true,
  "311_service_type": "What type of 311 request to open, or null if not applicable",
  "civic_response": "How to respond to citizens on the platform",
  "next_steps": ["step1", "step2", "step3"]
}}"""

    r = await openrouter.chat.completions.create(
        model="google/gemini-flash-1.5",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        response_format={"type": "json_object"},
    )
    return r.choices[0].message.content


# ── TOOL 5 ─────────────────────────────────────────────────────────────────────
@mcp.tool()
async def get_platform_summary() -> str:
    """
    Get a full summary of the Momentum MGM platform state.
    Total proposals, participation stats, and what Montgomery is talking about right now.
    """
    trends = json.loads(await analyze_trends())
    summary = {
        "platform": "Momentum MGM — Montgomery Civic Participation",
        "total_proposals": trends["total_proposals"],
        "top_issues": trends["top_by_votes"],
        "categories": list(CATEGORIES.keys()),
        "categories_detail": {k: {"label": v["label"], "color": v["color"]} for k, v in CATEGORIES.items()},
    }
    return json.dumps(summary, ensure_ascii=False, indent=2)


# ── TOOL 6 ─────────────────────────────────────────────────────────────────────
@mcp.tool()
async def get_montgomery_context(topic: str) -> str:
    """
    Query real Montgomery civic data for context on any topic.
    Sources: city news, mayor priorities, 311 data, category searches.
    Example: topic='public safety', topic='housing blight', topic='Mayor Reed 2026'
    Returns relevant excerpts from scraped Montgomery sources.
    """
    topic_lower = topic.lower()
    results = []

    # Load all scraped data files
    files = {
        "mayor_priorities": SCRAPED_DATA_DIR / "mayor_priorities.json",
        "category_searches": SCRAPED_DATA_DIR / "category_searches.json",
        "city_pages": SCRAPED_DATA_DIR / "city_pages.json",
        "311_data": SCRAPED_DATA_DIR / "311_data.json",
    }

    for source_name, fpath in files.items():
        if not fpath.exists():
            continue
        with open(fpath) as f:
            data = json.load(f)

        # Search results — match by title/description keywords
        if source_name == "category_searches":
            for category, items in data.items():
                if any(w in topic_lower for w in category.split("_")):
                    for r in items[:3]:
                        results.append({
                            "source": f"Montgomery civic data ({category})",
                            "title": r.get("title", ""),
                            "excerpt": r.get("description", "")[:300],
                            "url": r.get("url", ""),
                        })

        elif source_name == "mayor_priorities":
            for r in data.get("search_results", []):
                text = (r.get("title", "") + " " + r.get("description", "")).lower()
                if any(w in text for w in topic_lower.split()):
                    results.append({
                        "source": "Mayor Reed statements",
                        "title": r.get("title", ""),
                        "excerpt": r.get("description", "")[:300],
                        "url": r.get("url", ""),
                    })

        elif source_name == "city_pages":
            for page_key, page_data in data.items():
                content = page_data.get("content", "").lower()
                if any(w in content for w in topic_lower.split()):
                    excerpt = page_data.get("content", "")[:400]
                    results.append({
                        "source": f"City of Montgomery — {page_data.get('description', page_key)}",
                        "title": page_data.get("description", page_key),
                        "excerpt": excerpt,
                        "url": page_data.get("url", ""),
                    })

    if not results:
        return json.dumps({
            "topic": topic,
            "results": [],
            "note": "No direct matches in scraped data. Run scrape.py to refresh."
        }, indent=2)

    return json.dumps({
        "topic": topic,
        "results": results[:6],  # top 6 most relevant
        "sources_searched": list(files.keys()),
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
