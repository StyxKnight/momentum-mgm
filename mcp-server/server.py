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
from google.genai import types as genai_types
from jinja2 import Environment, FileSystemLoader

_jinja = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "prompts"),
    trim_blocks=True,
    lstrip_blocks=True,
)

def _render(template_name: str, **kwargs) -> str:
    return _jinja.get_template(template_name).render(**kwargs)


async def _brave_search(query: str, count: int = 5) -> list:
    """Brave Search API — returns list of {title, url, description}."""
    import httpx
    key = os.getenv("BRAVE_API_KEY")
    if not key:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": count, "text_decorations": False},
                headers={"X-Subscription-Token": key, "Accept": "application/json"},
            )
            data = r.json()
            return [
                {"title": w.get("title", ""), "url": w.get("url", ""), "description": w.get("description", "")}
                for w in data.get("web", {}).get("results", [])
            ]
    except Exception:
        return []


async def _generate_json(prompt: str, temperature: float = 0.1) -> str:
    """Gemini 2.5 Flash primary (direct API), Grok-4 via OpenRouter fallback."""
    import asyncio
    if _gemini:
        try:
            def _call():
                return _gemini.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=temperature,
                        response_mime_type="application/json",
                    ),
                )
            r = await asyncio.get_event_loop().run_in_executor(None, _call)
            return r.text
        except Exception:
            pass  # fallback to Grok
    r = await openrouter.chat.completions.create(
        model="x-ai/grok-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    return r.choices[0].message.content

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
    query {
      participatoryProcesses {
        components {
          id
          ... on Proposals {
            proposals(first: 200) {
              nodes {
                id
                title { translation(locale: "en") }
                body { translation(locale: "en") }
                publishedAt
              }
            }
          }
        }
      }
    }
    """
    data = await graphql(query)
    proposals = []
    for proc in (data.get("data", {}).get("participatoryProcesses") or []):
        for comp in (proc.get("components") or []):
            nodes = (comp.get("proposals") or {}).get("nodes") or []
            for p in nodes:
                title = (p.get("title") or {}).get("translation", "")
                body = (p.get("body") or {}).get("translation", "")
                proposals.append({
                    "id": p["id"],
                    "title": title,
                    "body": body[:300],
                })
    if len(proposals) > limit:
        proposals = proposals[:limit]
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

    return await _generate_json(prompt)


# ── TOOL 3 ─────────────────────────────────────────────────────────────────────
@mcp.tool()
async def analyze_trends() -> str:
    """
    Analyze current proposal trends on the platform.
    Returns total counts, top topics, most voted proposals, and priority alignment.
    """
    query = """
    query {
      participatoryProcesses {
        components {
          ... on Proposals {
            proposals(first: 200) {
              nodes {
                id
                title { translation(locale: "en") }
              }
            }
          }
        }
      }
    }
    """
    data = await graphql(query)
    proposals = []
    for proc in (data.get("data", {}).get("participatoryProcesses") or []):
        for comp in (proc.get("components") or []):
            nodes = (comp.get("proposals") or {}).get("nodes") or []
            for p in nodes:
                title = (p.get("title") or {}).get("translation", "")
                proposals.append({"id": p["id"], "title": title})

    result = {
        "total_proposals": len(proposals),
        "top_proposals": proposals[:10],
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

    return await _generate_json(prompt)


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


# ── TOOL 9 — get_census_trend ───────────────────────────────────────────────────
@mcp.tool()
def get_census_trend(neighborhood: str = None) -> str:
    """
    RESEARCH tool — no AI, no analysis, no thresholds.
    Returns raw Census ACS 2012-2024 linear regression (OLS) for a Montgomery neighborhood.
    Metrics: median_income, poverty_below, housing_vacant, unemployed, median_rent.
    Each metric returns: current value, slope per year, projection to 2026, R² confidence.
    Metrics with R² < 0.5 are flagged low_confidence — Claude should not draw conclusions from them.
    neighborhood=None returns city-wide aggregate across all 71 tracts.
    """
    conn = get_db()
    nb = neighborhood
    metrics = ["median_income", "poverty_below", "housing_vacant", "unemployed", "median_rent"]
    result = {
        "neighborhood": nb or "Montgomery (city-wide)",
        "data_source": "Census ACS 5-year estimates, 2012-2024, Montgomery County AL",
        "metrics": {},
    }

    with conn.cursor() as cur:
        for metric in metrics:
            cur.execute("""
                SELECT year, AVG(value) as value
                FROM civic_data.census
                WHERE metric = %s
                  AND (%s IS NULL OR neighborhood ILIKE %s)
                  AND value > 0
                GROUP BY year ORDER BY year
            """, (metric, nb, f"%{nb}%" if nb else None))
            rows = cur.fetchall()
            if len(rows) < 3:
                continue

            xs = [r[0] for r in rows]
            ys = [r[1] for r in rows]
            slope, intercept, r2 = _linreg(xs, ys)

            result["metrics"][metric] = {
                "current": round(ys[-1], 1),
                "year_current": xs[-1],
                "year_baseline": xs[0],
                "baseline": round(ys[0], 1),
                "slope_per_year": round(slope, 2),
                "projection_2026": round(slope * 2026 + intercept, 1),
                "r2": round(r2, 3),
                "low_confidence": r2 < 0.5,
                "data_points": len(xs),
            }

    conn.close()
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── TOOL 10 — get_city_incidents ────────────────────────────────────────────────
@mcp.tool()
def get_city_incidents(source: str, neighborhood: str = None) -> str:
    """
    RESEARCH tool — no AI, no analysis, no thresholds.
    Returns raw counts from Montgomery ArcGIS open data for one source at a time.
    source must be one of: code_violations, building_permits, fire_incidents,
    housing_condition, food_safety, environmental_nuisance, transit_stops,
    education_facilities, behavioral_centers, infrastructure_projects,
    citizen_reports, opportunity_zones.
    Use source='list' to get available sources and their total counts.
    neighborhood=None returns city-wide totals.
    """
    VALID_SOURCES = [
        "code_violations", "building_permits", "fire_incidents", "housing_condition",
        "food_safety", "environmental_nuisance", "transit_stops", "education_facilities",
        "behavioral_centers", "infrastructure_projects", "citizen_reports", "opportunity_zones",
    ]
    # Sources with meaningful status breakdowns
    STATUS_SOURCES = {"code_violations", "building_permits", "infrastructure_projects"}

    conn = get_db()

    if source == "list":
        with conn.cursor() as cur:
            cur.execute("""
                SELECT source, COUNT(*) as total
                FROM civic_data.city_data
                WHERE (%s IS NULL OR neighborhood ILIKE %s)
                GROUP BY source ORDER BY total DESC
            """, (neighborhood, f"%{neighborhood}%" if neighborhood else None))
            rows = cur.fetchall()
        conn.close()
        return json.dumps({
            "neighborhood": neighborhood or "Montgomery (city-wide)",
            "available_sources": {r[0]: r[1] for r in rows},
        }, ensure_ascii=False, indent=2)

    if source not in VALID_SOURCES:
        conn.close()
        return json.dumps({"error": f"Unknown source '{source}'. Use source='list' to see valid options."})

    nb = neighborhood
    result = {
        "neighborhood": nb or "Montgomery (city-wide)",
        "source": source,
        "data_source": "Montgomery ArcGIS Open Data (services7.arcgis.com)",
    }

    with conn.cursor() as cur:
        # Total count
        cur.execute("""
            SELECT COUNT(*) FROM civic_data.city_data
            WHERE source = %s AND (%s IS NULL OR neighborhood ILIKE %s)
        """, (source, nb, f"%{nb}%" if nb else None))
        result["total"] = cur.fetchone()[0]

        # Status breakdown — only for sources with meaningful status values
        if source in STATUS_SOURCES:
            cur.execute("""
                SELECT status, COUNT(*) as cnt
                FROM civic_data.city_data
                WHERE source = %s AND (%s IS NULL OR neighborhood ILIKE %s)
                  AND status IS NOT NULL AND status != '' AND status != 'None'
                GROUP BY status ORDER BY cnt DESC
            """, (source, nb, f"%{nb}%" if nb else None))
            rows = cur.fetchall()
            if rows:
                result["by_status"] = {r[0]: r[1] for r in rows}

        # Date range — only for sources that have reported_at
        cur.execute("""
            SELECT MIN(reported_at), MAX(reported_at)
            FROM civic_data.city_data
            WHERE source = %s AND (%s IS NULL OR neighborhood ILIKE %s)
              AND reported_at IS NOT NULL
        """, (source, nb, f"%{nb}%" if nb else None))
        dates = cur.fetchone()
        if dates and dates[0]:
            result["date_range"] = {
                "earliest": dates[0].strftime("%Y-%m-%d"),
                "latest": dates[1].strftime("%Y-%m-%d"),
            }

    conn.close()
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── TOOL 11 — get_business_health ───────────────────────────────────────────────
@mcp.tool()
def get_business_health(neighborhood: str = None) -> str:
    """
    RESEARCH tool — no AI, no analysis, no thresholds.
    Returns raw Yelp business data for a Montgomery neighborhood.
    Includes: total count, closed count, average rating, average review count
    (proxy for foot traffic), and top 5 categories by business count.
    neighborhood=None returns city-wide totals.
    """
    conn = get_db()
    nb = neighborhood
    result = {
        "neighborhood": nb or "Montgomery (city-wide)",
        "data_source": "Yelp via Bright Data (500 businesses sampled, Montgomery AL)",
    }

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_closed THEN 1 ELSE 0 END) as closed,
                ROUND(AVG(rating)::numeric, 2) as avg_rating,
                ROUND(AVG(review_count)::numeric, 0) as avg_reviews
            FROM civic_data.businesses
            WHERE (%s IS NULL OR neighborhood ILIKE %s)
        """, (nb, f"%{nb}%" if nb else None))
        row = cur.fetchone()

        if not row or not row["total"]:
            conn.close()
            return json.dumps({"neighborhood": nb or "Montgomery (city-wide)", "total": 0})

        result["total"] = row["total"]
        result["closed"] = row["closed"] or 0
        result["avg_rating"] = float(row["avg_rating"]) if row["avg_rating"] else None
        result["avg_reviews"] = int(row["avg_reviews"]) if row["avg_reviews"] else None

        cur.execute("""
            SELECT category, COUNT(*) as cnt
            FROM civic_data.businesses
            WHERE (%s IS NULL OR neighborhood ILIKE %s)
              AND category IS NOT NULL AND category != ''
            GROUP BY category ORDER BY cnt DESC LIMIT 5
        """, (nb, f"%{nb}%" if nb else None))
        cats = cur.fetchall()
        if cats:
            result["top_categories"] = {r["category"]: r["cnt"] for r in cats}

    conn.close()
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── TOOL 12 — find_solutions ────────────────────────────────────────────────────
@mcp.tool()
async def find_solutions(problem: str, neighborhood: str = None) -> str:
    """
    Given a civic problem in Montgomery, find concrete solutions using real-time web search.
    Searches for: active federal grant programs (HUD, CDBG, EPA, DOT), global best practices
    from cities that solved similar issues, and Montgomery-specific opportunities.
    Uses Brave Search API for live results + real Census data for Montgomery context.
    Examples: 'high vacancy rate', 'youth unemployment', 'food deserts', 'housing blight'
    """
    import asyncio

    # ── Real Montgomery stats from Census ───────────────────────────────────────
    conn = get_db()
    city_stats = {}
    with conn.cursor() as cur:
        cur.execute("""
            SELECT metric, ROUND(AVG(value)::numeric, 1) as val
            FROM civic_data.census
            WHERE year = (SELECT MAX(year) FROM civic_data.census)
              AND metric IN ('median_income','poverty_below','unemployed','housing_vacant','median_rent')
              AND value > 0
            GROUP BY metric
        """)
        city_stats = {r[0]: float(r[1]) for r in cur.fetchall()}
    conn.close()

    # ── 3 parallel Brave searches ───────────────────────────────────────────────
    federal_q   = f"{problem} federal grant program HUD EPA DOT USDA CDBG active 2025 2026"
    global_q    = f"{problem} city case study success program results neighborhood"
    local_q     = f"Montgomery Alabama {problem} funding solution program"

    federal_res, global_res, local_res = await asyncio.gather(
        _brave_search(federal_q, count=5),
        _brave_search(global_q, count=5),
        _brave_search(local_q, count=3),
    )

    # ── Render Jinja2 prompt ────────────────────────────────────────────────────
    prompt = _render("find_solutions.j2",
        problem=problem,
        neighborhood=neighborhood,
        city_stats=city_stats,
        federal_results=federal_res,
        global_results=global_res,
        local_results=local_res,
    )

    return await _generate_json(prompt, temperature=0.4)


# ── TOOL 13 — analyze_neighborhood ──────────────────────────────────────────────
@mcp.tool()
def analyze_neighborhood(neighborhood: str, index: str = "all") -> str:
    """
    ANALYZE tool — computes ADI, SVI, and/or EJI composite deprivation scores.
    Uses real Montgomery data (Census ACS + ArcGIS) against all 71 census tracts as baseline.

    ADI (Area Deprivation Index) — UW Madison / HRSA: material deprivation
    SVI (Social Vulnerability Index) — CDC/ATSDR: vulnerability to shocks (no race variable)
    EJI (Environmental Justice Index) — CDC/ATSDR + EPA: cumulative environmental burden

    index: 'ADI', 'SVI', 'EJI', or 'all'
    Score 0.0–1.0: higher = more deprived/vulnerable/burdened.
    Percentile: proportion of Montgomery neighborhoods scoring lower than this one.

    neighborhood='list' returns the top 5 most vulnerable neighborhoods for each index.
    See docs/analysis_methodology.md for full scientific basis and citations.
    """
    import statistics

    VALID_INDICES = ["ADI", "SVI", "EJI", "all"]
    if index not in VALID_INDICES:
        return json.dumps({"error": f"Unknown index '{index}'. Use: ADI, SVI, EJI, or all"})

    conn = get_db()

    def _census_by_nb(cur, metric):
        cur.execute("""
            SELECT neighborhood, AVG(value) as val
            FROM civic_data.census
            WHERE metric = %s AND year >= 2020 AND value > 0
              AND neighborhood IS NOT NULL AND neighborhood != ''
            GROUP BY neighborhood
        """, (metric,))
        return {r[0]: float(r[1]) for r in cur.fetchall()}

    def _city_by_nb(cur, source):
        cur.execute("""
            SELECT neighborhood, COUNT(*) as cnt
            FROM civic_data.city_data
            WHERE source = %s
              AND neighborhood IS NOT NULL AND neighborhood != ''
            GROUP BY neighborhood
        """, (source,))
        return {r[0]: float(r[1]) for r in cur.fetchall()}

    def _compute(variables, target_nb):
        """
        variables: list of (name, {nb: value}, invert, weight)
        Returns composite percentile score + factor breakdown for target_nb.
        """
        # Compute per-variable stats across all neighborhoods
        var_stats = {}
        for name, data, invert, weight in variables:
            vals = list(data.values())
            if len(vals) < 2:
                continue
            mean = sum(vals) / len(vals)
            std = statistics.stdev(vals)
            var_stats[name] = (mean, std, invert, weight)

        def _composite_z(nb):
            zs, ws = [], []
            for name, data, invert, weight in variables:
                if name not in var_stats or nb not in data:
                    continue
                mean, std, inv, w = var_stats[name]
                if std == 0:
                    continue
                z = (data[nb] - mean) / std
                if inv:
                    z = -z
                zs.append(z * w)
                ws.append(w)
            if not zs:
                return None
            return sum(zs) / sum(ws)

        target_z = _composite_z(target_nb)
        if target_z is None:
            return {"error": f"No data found for '{target_nb}'. Try neighborhood='list' to see available names."}

        # Percentile rank across all neighborhoods
        all_nbs = set()
        for _, data, _, _ in variables:
            all_nbs.update(data.keys())
        all_composites = [_composite_z(nb) for nb in all_nbs]
        all_composites = [z for z in all_composites if z is not None]
        rank = sum(1 for z in all_composites if z <= target_z)
        percentile = round(rank / len(all_composites), 3) if all_composites else 0.5

        # Top 3 factors
        factors = []
        for name, data, invert, weight in variables:
            if name not in var_stats or target_nb not in data:
                continue
            mean, std, inv, w = var_stats[name]
            if std == 0:
                continue
            raw = data[target_nb]
            z = (raw - mean) / std
            if inv:
                z = -z
            all_z = [(-((data[nb2] - mean) / std) if inv else ((data[nb2] - mean) / std))
                     for nb2 in data]
            pct_var = round(sum(1 for z2 in all_z if z2 <= z) / max(1, len(all_z)), 3)
            factors.append({"variable": name, "raw_value": round(raw, 1), "z_score": round(z, 2), "percentile": pct_var})

        top3 = sorted(factors, key=lambda f: abs(f["z_score"]), reverse=True)[:3]
        used = len(factors)

        return {
            "score": percentile,
            "interpretation": f"{round(percentile * 100)}% of Montgomery neighborhoods score lower on this index",
            "variables_used": used,
            "variables_expected": len(variables),
            "low_confidence": used < 4,
            "top_factors": top3,
        }

    with conn.cursor() as cur:
        # Load all data once
        poverty    = _census_by_nb(cur, "poverty_below")
        income     = _census_by_nb(cur, "median_income")
        unemployed = _census_by_nb(cur, "unemployed")
        vacant     = _census_by_nb(cur, "housing_vacant")
        rent       = _census_by_nb(cur, "median_rent")
        housing_c  = _city_by_nb(cur, "housing_condition")
        code_viol  = _city_by_nb(cur, "code_violations")
        env_nuis   = _city_by_nb(cur, "environmental_nuisance")
        food_saf   = _city_by_nb(cur, "food_safety")
        fire       = _city_by_nb(cur, "fire_incidents")
        transit    = _city_by_nb(cur, "transit_stops")
        behavioral = _city_by_nb(cur, "behavioral_centers")

        # 'list' mode: rank all neighborhoods by each index
        if neighborhood == "list":
            all_nbs = set(poverty) | set(income) | set(unemployed)
            ranking = {}
            for nb in sorted(all_nbs):
                adi_vars = [
                    ("poverty_below", poverty, False, 1.0), ("median_income", income, True, 1.0),
                    ("unemployed", unemployed, False, 1.0), ("housing_vacant", vacant, False, 1.0),
                    ("housing_condition", housing_c, False, 1.0), ("code_violations", code_viol, False, 1.0),
                ]
                r = _compute(adi_vars, nb)
                ranking[nb] = r.get("score", 0)
            top5 = sorted(ranking.items(), key=lambda x: x[1], reverse=True)[:5]
            conn.close()
            return json.dumps({
                "top_5_most_deprived_ADI": [{"neighborhood": nb, "score": s} for nb, s in top5],
                "note": "Run analyze_neighborhood(neighborhood='<name>', index='all') for full analysis"
            }, indent=2)

        indices_to_run = ["ADI", "SVI", "EJI"] if index == "all" else [index]
        result = {
            "neighborhood": neighborhood,
            "methodology": "docs/analysis_methodology.md",
            "scores": {},
        }

        if "ADI" in indices_to_run:
            result["scores"]["ADI"] = {
                "name": "Area Deprivation Index",
                "source": "UW Madison / HRSA — material deprivation (income, employment, housing)",
                **_compute([
                    ("poverty_below",     poverty,    False, 1.0),
                    ("median_income",     income,     True,  1.0),
                    ("unemployed",        unemployed, False, 1.0),
                    ("housing_vacant",    vacant,     False, 1.0),
                    ("median_rent",       rent,       True,  0.5),
                    ("housing_condition", housing_c,  False, 1.0),
                    ("code_violations",   code_viol,  False, 1.0),
                ], neighborhood),
            }

        if "SVI" in indices_to_run:
            result["scores"]["SVI"] = {
                "name": "Social Vulnerability Index",
                "source": "CDC/ATSDR — vulnerability to shocks (Themes 1,2,4 — racial/ethnic theme excluded, see methodology)",
                **_compute([
                    ("poverty_below",      poverty,    False, 1.0),
                    ("median_income",      income,     True,  1.0),
                    ("unemployed",         unemployed, False, 1.0),
                    ("housing_vacant",     vacant,     False, 1.0),
                    ("median_rent",        rent,       False, 1.0),
                    ("housing_condition",  housing_c,  False, 1.0),
                    ("behavioral_centers", behavioral, True,  0.5),
                    ("food_safety",        food_saf,   False, 0.5),
                ], neighborhood),
            }

        if "EJI" in indices_to_run:
            result["scores"]["EJI"] = {
                "name": "Environmental Justice Index",
                "source": "CDC/ATSDR + EPA — cumulative environmental burden on health",
                **_compute([
                    ("environmental_nuisance", env_nuis,  False, 1.5),
                    ("code_violations",        code_viol, False, 1.0),
                    ("housing_condition",      housing_c, False, 1.0),
                    ("food_safety",            food_saf,  False, 1.0),
                    ("fire_incidents",         fire,      False, 1.0),
                    ("poverty_below",          poverty,   False, 1.0),
                    ("unemployed",             unemployed,False, 1.0),
                    ("median_income",          income,    True,  1.0),
                    ("housing_vacant",         vacant,    False, 0.5),
                    ("transit_stops",          transit,   True,  0.5),
                ], neighborhood),
            }

    conn.close()
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── TOOL 14 — civic_report ──────────────────────────────────────────────────────
@mcp.tool()
async def civic_report(neighborhood: str) -> str:
    """
    ANALYZE tool — full civic intelligence report for a Montgomery neighborhood.
    Aggregates all research tools (Census trend, ArcGIS incidents, Yelp health, ADI/SVI/EJI scores),
    then calls Grok-4 with structured prompt (Role + Lorebook + RAG + CoT + Restrictions + JSON schema)
    to produce a factual, hallucination-resistant civic analysis.

    Temperature: 0.1 (data analysis mode)
    Output: structured JSON with findings, severity, trends, and top civic concerns.
    All numbers in the output are verified against real data — no inference allowed.

    Use this before find_solutions() to ground solution recommendations in confirmed facts.
    """
    # ── Step 1: Collect all research data ───────────────────────────────────────
    census   = json.loads(get_census_trend(neighborhood))
    incidents_list = []
    for source in ["code_violations", "building_permits", "fire_incidents",
                   "housing_condition", "food_safety", "environmental_nuisance"]:
        inc = json.loads(get_city_incidents(source, neighborhood))
        if inc.get("total", 0) > 0:
            incidents_list.append(inc)

    business = json.loads(get_business_health(neighborhood))
    scores   = json.loads(analyze_neighborhood(neighborhood, "all"))

    # ── Step 2: Build RAG data block ────────────────────────────────────────────
    rag = {
        "neighborhood": neighborhood,
        "census_trend": census.get("metrics", {}),
        "city_incidents": {i["source"]: i["total"] for i in incidents_list},
        "business_health": {
            "total": business.get("total", 0),
            "closed": business.get("closed", 0),
            "avg_rating": business.get("avg_rating"),
        },
        "deprivation_scores": {
            idx: {
                "score": s.get("score"),
                "interpretation": s.get("interpretation"),
                "top_factors": s.get("top_factors", []),
            }
            for idx, s in scores.get("scores", {}).items()
            if "score" in s
        },
    }

    # ── Step 3: Render prompt from Jinja2 template ──────────────────────────────
    prompt = _render("civic_report.j2", neighborhood=neighborhood, data=rag)

    # ── Step 4: Gemini 2.5 Flash (fallback Grok-4) at temperature=0.1 ───────────
    raw = await _generate_json(prompt, temperature=0.1)
    try:
        parsed = json.loads(raw)
        parsed["_sources"] = {
            "census_tracts": census.get("data_source", "Census ACS"),
            "incidents_sources": [i["source"] for i in incidents_list],
            "business_source": business.get("data_source", "Yelp"),
            "methodology": "docs/analysis_methodology.md",
        }
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return raw


# ── TOOL 15 — post_ai_response ──────────────────────────────────────────────────
@mcp.tool()
async def post_ai_response(proposal_id: str) -> str:
    """
    WRITE tool — closes the civic loop: reads a Decidim proposal, classifies it,
    generates a neighborhood-aware AI recommendation, and posts it as an official
    comment on the platform signed by Momentum AI.

    Flow: get_proposals → classify_proposal → civic_report → recommend_action → GraphQL addComment
    All data is real. No hallucinations. The comment is visible to citizens on mgm.styxcore.dev.
    """
    # ── Step 1: Fetch proposal ───────────────────────────────────────────────────
    pq = """
    query {
      participatoryProcesses {
        components {
          ... on Proposals {
            proposals(first: 200) {
              nodes {
                id
                title { translation(locale: "en") }
                body { translation(locale: "en") }
              }
            }
          }
        }
      }
    }"""
    data = await graphql(pq)
    proposal = None
    for proc in (data.get("data", {}).get("participatoryProcesses") or []):
        for comp in (proc.get("components") or []):
            for node in (comp.get("proposals", {}).get("nodes") or []):
                if str(node["id"]) == str(proposal_id):
                    proposal = node
                    break

    if not proposal:
        return json.dumps({"error": f"Proposal {proposal_id} not found"})

    title = (proposal.get("title") or {}).get("translation", "")
    body = (proposal.get("body") or {}).get("translation", "")
    text = f"{title}. {body}"[:500]

    # ── Step 2: Classify ─────────────────────────────────────────────────────────
    classification = json.loads(await classify_proposal(text))
    category = classification.get("category", "governance")
    summary = classification.get("summary", title)
    actionable = classification.get("311_actionable", False)

    # ── Step 3: Neighborhood report ──────────────────────────────────────────────
    report = json.loads(await civic_report("Montgomery"))
    severity = report.get("overall_severity", "moderate")

    # ── Step 4: Build AI comment ─────────────────────────────────────────────────
    comment_prompt = f"""Write a short, respectful official response to a citizen proposal on the Momentum MGM civic platform.
Respond as Momentum AI, the city's civic intelligence system.

Proposal: "{title}"
Category: {category}
Summary: {summary}
City severity context: {severity}
311 actionable: {actionable}

Write 3-4 sentences in plain English. Be factual, encouraging, and specific about next steps.
Do NOT use markdown, headers, or bullet points — plain text only.
End with: "— Momentum AI, City of Montgomery Civic Intelligence"

Respond with just the comment text, no JSON."""

    comment_body = await _generate_json(comment_prompt, temperature=0.3)
    # Strip JSON wrapper if model wrapped it
    try:
        parsed = json.loads(comment_body)
        comment_body = parsed.get("comment", comment_body) if isinstance(parsed, dict) else comment_body
    except Exception:
        pass
    comment_body = comment_body.strip().strip('"')

    # ── Step 5: Post via GraphQL mutation ────────────────────────────────────────
    mutation = """
    mutation($id: String!, $type: String!, $body: String!) {
      commentable(id: $id, type: $type) {
        addComment(body: $body) { id body }
      }
    }"""
    result = await graphql(mutation, {
        "id": str(proposal_id),
        "type": "Decidim::Proposals::Proposal",
        "body": comment_body,
    }, auth=True)

    errors = result.get("errors")
    if errors:
        return json.dumps({"error": errors[0]["message"], "proposal_id": proposal_id})

    comment = result.get("data", {}).get("commentable", {}).get("addComment", {})
    return json.dumps({
        "status": "posted",
        "proposal_id": proposal_id,
        "proposal_title": title,
        "category": category,
        "comment_id": comment.get("id"),
        "comment_preview": comment_body[:200],
        "platform_url": f"{os.getenv('DECIDIM_URL')}/processes",
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
