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
import psycopg2
import psycopg2.extras
from google import genai as google_genai

load_dotenv()

DB = {
    "host": "127.0.0.1", "port": 5432,
    "dbname": "momentum", "user": "nodebb", "password": "superSecret123",
}

_gemini = google_genai.Client(api_key=os.getenv("GOOGLE_API_KEY")) if os.getenv("GOOGLE_API_KEY") else None


def get_db():
    return psycopg2.connect(**DB)


def _embed(text: str):
    """Embed via gemini-embedding-001 (3072d). Returns list or None."""
    if not _gemini:
        return None
    try:
        r = _gemini.models.embed_content(model="models/gemini-embedding-001", contents=text)
        return r.embeddings[0].values
    except Exception:
        return None


def _linreg(xs: list, ys: list) -> tuple:
    """OLS linear regression. Returns (slope, intercept, r2)."""
    n = len(xs)
    if n < 2:
        return 0.0, ys[0] if ys else 0.0, 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    ss_xy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    ss_xx = sum((x - mx) ** 2 for x in xs)
    if ss_xx == 0:
        return 0.0, my, 1.0
    slope = ss_xy / ss_xx
    intercept = my - slope * mx
    y_pred = [slope * x + intercept for x in xs]
    ss_res = sum((y - yp) ** 2 for y, yp in zip(ys, y_pred))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    return slope, intercept, r2

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


# ── TOOL 7 ─────────────────────────────────────────────────────────────────────
@mcp.tool()
def get_neighborhood_intelligence(neighborhood: str) -> str:
    """
    Comprehensive intelligence report for a Montgomery neighborhood.
    Aggregates Census ACS trends, Zillow housing prices, Yelp business health,
    and Indeed job market data into a single structured report.
    Use neighborhood='all' for city-wide summary.
    """
    conn = get_db()
    report = {"neighborhood": neighborhood, "sources": {}}

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Census: latest year metrics
        tract_filter = "" if neighborhood == "all" else "AND neighborhood ILIKE %s"
        params_n = (f"%{neighborhood}%",) if neighborhood != "all" else ()

        cur.execute(f"""
            SELECT metric, AVG(value) as value, MAX(year) as year
            FROM civic_data.census
            WHERE year = (SELECT MAX(year) FROM civic_data.census)
            {tract_filter}
            GROUP BY metric
        """, params_n)
        census_latest = {r["metric"]: round(r["value"], 1) for r in cur.fetchall()}
        report["sources"]["census_latest"] = census_latest

        # Census: income trend 2012→now
        cur.execute(f"""
            SELECT year, AVG(value) as value
            FROM civic_data.census
            WHERE metric = 'median_income' {tract_filter}
            GROUP BY year ORDER BY year
        """, params_n)
        income_rows = cur.fetchall()
        if income_rows:
            report["sources"]["income_trend"] = {
                "2012": round(income_rows[0]["value"]),
                "latest": round(income_rows[-1]["value"]),
                "change_pct": round((income_rows[-1]["value"] - income_rows[0]["value"]) / income_rows[0]["value"] * 100, 1),
            }

        # Zillow: housing prices
        cur.execute("""
            SELECT COUNT(*) as count, AVG(price) as avg_price,
                   MIN(price) as min_price, MAX(price) as max_price,
                   AVG(days_on_market) as avg_dom
            FROM civic_data.properties
            WHERE source = 'zillow' AND price > 0
            AND (%s OR neighborhood ILIKE %s)
        """, (neighborhood == "all", f"%{neighborhood}%"))
        zillow = cur.fetchone()
        if zillow and zillow["count"]:
            report["sources"]["housing"] = {
                "listings": zillow["count"],
                "avg_price": round(zillow["avg_price"]) if zillow["avg_price"] else None,
                "min_price": round(zillow["min_price"]) if zillow["min_price"] else None,
                "max_price": round(zillow["max_price"]) if zillow["max_price"] else None,
                "avg_days_on_market": round(zillow["avg_dom"]) if zillow["avg_dom"] else None,
            }

        # Yelp: business health
        cur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN is_closed THEN 1 ELSE 0 END) as closed,
                   AVG(rating) as avg_rating,
                   AVG(review_count) as avg_reviews
            FROM civic_data.businesses
            WHERE source = 'yelp'
            AND (%s OR neighborhood ILIKE %s)
        """, (neighborhood == "all", f"%{neighborhood}%"))
        yelp = cur.fetchone()
        if yelp and yelp["total"]:
            report["sources"]["businesses"] = {
                "total": yelp["total"],
                "closed": yelp["closed"],
                "closure_rate_pct": round(yelp["closed"] / yelp["total"] * 100, 1),
                "avg_rating": round(yelp["avg_rating"], 2) if yelp["avg_rating"] else None,
                "avg_reviews": round(yelp["avg_reviews"]) if yelp["avg_reviews"] else None,
            }

        # Indeed: jobs
        cur.execute("""
            SELECT COUNT(*) as count,
                   AVG(salary_min) as avg_sal_min,
                   AVG(salary_max) as avg_sal_max
            FROM civic_data.jobs
            WHERE source = 'indeed'
        """)
        indeed = cur.fetchone()
        if indeed and indeed["count"]:
            report["sources"]["jobs"] = {
                "listings": indeed["count"],
                "avg_salary_min": round(indeed["avg_sal_min"]) if indeed["avg_sal_min"] else None,
                "avg_salary_max": round(indeed["avg_sal_max"]) if indeed["avg_sal_max"] else None,
            }

    conn.close()
    return json.dumps(report, ensure_ascii=False, indent=2)


# ── TOOL 8 ─────────────────────────────────────────────────────────────────────
@mcp.tool()
def semantic_civic_search(query: str, neighborhood: str = None) -> str:
    """
    Semantic search across all Montgomery civic data using pgvector cosine similarity.
    Finds relevant properties, businesses, reviews, and jobs matching the query concept.
    Embeds query with gemini-embedding-001 (3072d) then searches civic_data.embeddings.
    Examples: 'abandoned buildings', 'jobs paying over 50k', 'highly rated restaurants closing'
    """
    vec = _embed(query)
    if not vec:
        return json.dumps({"error": "Embedding unavailable — check GOOGLE_API_KEY"})

    vec_str = "[" + ",".join(str(v) for v in vec) + "]"
    conn = get_db()

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """
            SELECT source_table, source_id, neighborhood, civic_category,
                   content_text, 1 - (embedding <=> %s::vector) AS similarity
            FROM civic_data.embeddings
            WHERE (%s IS NULL OR neighborhood ILIKE %s)
            ORDER BY embedding <=> %s::vector
            LIMIT 10
        """
        cur.execute(sql, (vec_str, neighborhood, f"%{neighborhood}%" if neighborhood else None, vec_str))
        rows = cur.fetchall()

    conn.close()
    results = [
        {
            "source": r["source_table"],
            "neighborhood": r["neighborhood"],
            "category": r["civic_category"],
            "content": r["content_text"],
            "similarity": round(r["similarity"], 3),
        }
        for r in rows
    ]
    return json.dumps({"query": query, "results": results}, ensure_ascii=False, indent=2)


# ── TOOL 9 ─────────────────────────────────────────────────────────────────────
@mcp.tool()
def get_neighborhood_velocity(neighborhood: str = None) -> str:
    """
    Linear regression on Census ACS 2012-2024 time series to measure neighborhood velocity.
    Returns rate of change per year and 2-year projection (2026) for key metrics.
    High negative velocity on income + high vacancy = urgency signal for intervention.
    neighborhood=None returns city-wide aggregate.
    """
    conn = get_db()
    metrics = ["median_income", "poverty_below", "housing_vacant", "unemployed", "median_rent"]
    result = {"neighborhood": neighborhood or "Montgomery (city-wide)", "velocity": {}}

    with conn.cursor() as cur:
        for metric in metrics:
            cur.execute("""
                SELECT year, AVG(value) as value
                FROM civic_data.census
                WHERE metric = %s AND (%s IS NULL OR neighborhood ILIKE %s)
                  AND value > 0
                GROUP BY year ORDER BY year
            """, (metric, neighborhood, f"%{neighborhood}%" if neighborhood else None))
            rows = cur.fetchall()
            if len(rows) < 3:
                continue

            xs = [r[0] for r in rows]
            ys = [r[1] for r in rows]
            slope, intercept, r2 = _linreg(xs, ys)
            current = ys[-1]
            projection_2026 = slope * 2026 + intercept

            result["velocity"][metric] = {
                "current": round(current, 1),
                "slope_per_year": round(slope, 1),
                "direction": "improving" if slope > 0 else "declining",
                "projection_2026": round(projection_2026, 1),
                "confidence_r2": round(r2, 3),
            }

    conn.close()

    # Urgency score: declining income + rising vacancy + rising unemployment
    v = result["velocity"]
    urgency_signals = []
    if v.get("median_income", {}).get("slope_per_year", 1) < 0:
        urgency_signals.append("income declining")
    if v.get("housing_vacant", {}).get("slope_per_year", 0) > 0:
        urgency_signals.append("vacancy rising")
    if v.get("unemployed", {}).get("slope_per_year", 0) > 0:
        urgency_signals.append("unemployment rising")

    result["urgency"] = "high" if len(urgency_signals) >= 2 else "medium" if urgency_signals else "low"
    result["urgency_signals"] = urgency_signals

    return json.dumps(result, ensure_ascii=False, indent=2)


# ── TOOL 10 ────────────────────────────────────────────────────────────────────
@mcp.tool()
async def find_solutions(problem: str, neighborhood: str = None) -> str:
    """
    Given a civic problem in Montgomery, find concrete solutions:
    federal grant programs (HUD, CDBG, EPA, DOT), comparable cities that solved
    similar issues, and specific recommendations for Montgomery's context.
    Examples: 'high vacancy rate in West Montgomery', 'youth unemployment in North Montgomery'
    """
    context = f"Neighborhood: {neighborhood}" if neighborhood else "City-wide (Montgomery, AL)"
    prompt = f"""You are a civic policy expert advising the City of Montgomery, Alabama.

Problem: {problem}
Context: {context}
Montgomery facts: population ~200K, median income ~$47K, poverty rate ~22%, 71 census tracts.

Provide actionable solutions in JSON:
{{
  "federal_programs": [
    {{
      "name": "Program name",
      "agency": "HUD / EPA / DOT / USDA / etc.",
      "description": "What it funds",
      "eligibility": "Key eligibility criteria",
      "typical_grant": "$X - $Y",
      "apply_url_hint": "Where to find application info"
    }}
  ],
  "comparable_cities": [
    {{
      "city": "City, State",
      "problem_solved": "Similar issue they addressed",
      "approach": "What they did",
      "outcome": "Measurable result"
    }}
  ],
  "montgomery_recommendations": [
    "Specific actionable step 1",
    "Specific actionable step 2",
    "Specific actionable step 3"
  ],
  "urgency": "high|medium|low",
  "estimated_timeline": "X months/years to see impact"
}}"""

    r = await openrouter.chat.completions.create(
        model="x-ai/grok-4",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    return r.choices[0].message.content


if __name__ == "__main__":
    mcp.run()
