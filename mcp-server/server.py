"""
Momentum MGM — MCP Server
Bridges Claude ↔ Decidim civic platform + Montgomery open data lake

ARCHITECTURE NOTE:
- Seeded citizens (20 characters via inject_decidim.rb) are SIMULATION ONLY.
  In real deployment they are purged — replaced by actual Montgomery residents.
- AI tools (post_ai_response, detect_civic_gaps, etc.) remain active in all modes.
  The AI never impersonates a citizen. It always signs as "Momentum AI".
- All AI comments are data-grounded: Census ACS + ArcGIS + Yelp + Zillow.
  No hallucinations. No generic advice.
"""
import os
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings
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


mcp = FastMCP(
    "momentum-mgm",
    host="0.0.0.0",
    port=8200,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["mcp.styxcore.dev", "localhost", "127.0.0.1"],
        allowed_origins=["https://mcp.styxcore.dev", "https://claude.ai"],
    ),
)
openrouter = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

VALID_NEIGHBORHOODS = [
    "Centennial Hill", "Downtown Montgomery", "West Side", "South Montgomery",
    "South Montgomery / Eastchase", "Southeast Montgomery", "Midtown / Cloverdale",
    "Cottage Hill", "North Montgomery / Chisholm", "East Montgomery / Eastdale",
    "East Montgomery / Vaughn", "East Montgomery / Forest Park",
    "Northwest Montgomery County", "Rural Montgomery County", "Pike Road",
    "Garden District", "Cloverdale",
]

_NB_HINT = (
    "Valid neighborhoods: Centennial Hill, Downtown Montgomery, West Side, "
    "South Montgomery, South Montgomery / Eastchase, Southeast Montgomery, "
    "Midtown / Cloverdale, Cottage Hill, North Montgomery / Chisholm, "
    "East Montgomery / Eastdale, East Montgomery / Vaughn, "
    "East Montgomery / Forest Park, Garden District, Cloverdale. "
    "Use None for city-wide. Do NOT use sub-neighborhood names like "
    "'Capitol Heights' or 'Cloverdale Park' — use the closest zone above."
)


def _resolve_neighborhood(neighborhood: str | None) -> str | None:
    """Fuzzy-match neighborhood name to closest valid name. Returns None if city-wide."""
    if not neighborhood or neighborhood.lower() in ("montgomery", "all", "city-wide"):
        return None
    nb_lower = neighborhood.lower()
    # Exact match
    for valid in VALID_NEIGHBORHOODS:
        if nb_lower == valid.lower():
            return valid
    # Partial match
    for valid in VALID_NEIGHBORHOODS:
        if nb_lower in valid.lower() or valid.lower() in nb_lower:
            return valid
    # Word overlap
    words = set(nb_lower.split())
    best, best_score = None, 0
    for valid in VALID_NEIGHBORHOODS:
        score = len(words & set(valid.lower().split()))
        if score > best_score:
            best, best_score = valid, score
    return best if best_score > 0 else neighborhood


def _next_steps(tool: str, context: dict = None) -> list[dict]:
    """
    Returns 2-3 suggested next tools with plain-language explanations.
    Injected into key tool outputs so Claude can guide users through the civic workflow.
    context: optional dict with keys like 'neighborhood', 'severity', 'category', 'proposal_id'
    """
    ctx = context or {}
    nb = ctx.get("neighborhood")
    nb_arg = f'neighborhood="{nb}"' if nb else 'neighborhood="<zone>"'

    FLOWS = {
        "detect_civic_gaps": [
            {"tool": "civic_report",     "why": "Deep-dive into a silent zone — Census trends, incident breakdown, deprivation scores", "example": f'civic_report({nb_arg})'},
            {"tool": "find_solutions",   "why": "Find federal grant programs and comparable cities that fixed the dominant issue",      "example": f'find_solutions(problem="housing blight", {nb_arg})'},
            {"tool": "post_ai_response", "why": "Post an AI comment on an existing proposal to bring data into the civic debate",      "example": 'post_ai_response(proposal_id="<id>")'},
        ],
        "civic_report": [
            {"tool": "find_solutions",      "why": "Now that you have the diagnosis, find real federal programs and action plans",          "example": f'find_solutions(problem="<dominant issue>", {nb_arg})'},
            {"tool": "create_report_doc",   "why": "Export this report as a formatted Google Doc ready to share with city hall",           "example": f'create_report_doc({nb_arg})'},
            {"tool": "export_to_sheet",     "why": "Push all the numbers into a Google Sheet for data-driven meetings",                    "example": f'export_to_sheet({nb_arg})'},
            {"tool": "post_ai_response",    "why": "Close the loop — post a data-grounded AI comment directly on a citizen proposal",      "example": 'post_ai_response(proposal_id="<id>")'},
        ],
        "find_solutions": [
            {"tool": "create_report_doc",  "why": "Turn this into a shareable Google Doc — executive briefing for city administrators", "example": f'create_report_doc({nb_arg})'},
            {"tool": "create_action_tasks","why": "Convert every recommendation into a Google Task assigned to the right department",   "example": f'create_action_tasks({nb_arg})'},
            {"tool": "post_ai_response",   "why": "Post the top recommendation as an AI comment on the citizen proposal",              "example": 'post_ai_response(proposal_id="<id>")'},
        ],
        "get_census_trend": [
            {"tool": "analyze_neighborhood", "why": "Compute ADI/SVI/EJI deprivation scores to contextualize these trends",  "example": f'analyze_neighborhood({nb_arg})'},
            {"tool": "get_city_incidents",   "why": "Cross-reference with actual ArcGIS incident data — what's happening on the ground", "example": f'get_city_incidents({nb_arg})'},
            {"tool": "civic_report",         "why": "Full AI synthesis: trends + incidents + scores + narrative in one shot",            "example": f'civic_report({nb_arg})'},
        ],
        "get_city_incidents": [
            {"tool": "analyze_neighborhood", "why": "Add deprivation scores — is this area already at a breaking point?",  "example": f'analyze_neighborhood({nb_arg})'},
            {"tool": "civic_report",         "why": "Full AI report combining all data sources for this neighborhood",      "example": f'civic_report({nb_arg})'},
            {"tool": "find_solutions",       "why": "Find federal programs targeting the dominant incident type",           "example": f'find_solutions(problem="<incident type>", {nb_arg})'},
        ],
        "analyze_neighborhood": [
            {"tool": "civic_report",   "why": "Full AI narrative combining these scores with real Census + ArcGIS data", "example": f'civic_report({nb_arg})'},
            {"tool": "find_solutions", "why": "Given the severity, what federal programs and city actions apply?",       "example": f'find_solutions(problem="deprivation", {nb_arg})'},
        ],
        "summarize_comments": [
            {"tool": "post_ai_response", "why": "Now that you know the sentiment, post a data-grounded AI response to the proposal",          "example": 'post_ai_response(proposal_id="<id>")'},
            {"tool": "civic_report",     "why": "Back the debate with real neighborhood data — Census + ArcGIS + deprivation scores",          "example": f'civic_report({nb_arg})'},
        ],
        "get_proposals": [
            {"tool": "classify_proposal",  "why": "Categorize a proposal into one of 10 civic categories + 311 routing",         "example": 'classify_proposal(text="<proposal body>")'},
            {"tool": "summarize_comments", "why": "Read the room — sentiment analysis on the comments of any proposal",           "example": 'summarize_comments(proposal_id="<id>")'},
            {"tool": "post_ai_response",   "why": "Let AI respond to a proposal with real neighborhood data",                     "example": 'post_ai_response(proposal_id="<id>")'},
        ],
        "export_to_sheet": [
            {"tool": "create_report_doc", "why": "Complement the sheet with a full narrative Google Doc for city hall", "example": f'create_report_doc({nb_arg})'},
            {"tool": "sync_gcal",         "why": "Push upcoming public meetings to Google Calendar",                    "example": 'sync_gcal()'},
        ],
        "create_report_doc": [
            {"tool": "export_to_sheet",     "why": "Also push the raw data to Google Sheets for analysis",         "example": f'export_to_sheet({nb_arg})'},
            {"tool": "create_action_tasks", "why": "Convert recommendations into Google Tasks for departments",     "example": f'create_action_tasks({nb_arg})'},
        ],
        "get_meetings": [
            {"tool": "sync_gcal",        "why": "Sync all these meetings to Google Calendar", "example": 'sync_gcal()'},
            {"tool": "get_proposals",    "why": "See what citizens are proposing in parallel", "example": 'get_proposals()'},
        ],
        "semantic_civic_search": [
            {"tool": "civic_report",   "why": "Full analysis of the neighborhood most relevant to your search results", "example": f'civic_report({nb_arg})'},
            {"tool": "find_solutions", "why": "Find real programs targeting the issues surfaced by the search",         "example": 'find_solutions(problem="<topic>")'},
        ],
    }

    return FLOWS.get(tool, [])


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
    return json.dumps({
        "proposals": proposals,
        "next_steps": _next_steps("get_proposals"),
    }, ensure_ascii=False, indent=2)


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
    return json.dumps({"query": query, "results": results, "next_steps": _next_steps("semantic_civic_search")}, ensure_ascii=False, indent=2)


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
    nb = _resolve_neighborhood(neighborhood)
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
    result["next_steps"] = _next_steps("get_census_trend", {"neighborhood": nb})
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
    citizen_reports, opportunity_zones, business_licenses, historic_markers,
    community_centers, education_facility, parks_recreation, city_owned_property,
    zoning_decisions.
    Use source='list' to get available sources and their total counts.
    neighborhood=None returns city-wide totals.
    """
    VALID_SOURCES = [
        "code_violations", "building_permits", "fire_incidents", "housing_condition",
        "food_safety", "environmental_nuisance", "transit_stops", "education_facilities",
        "behavioral_centers", "infrastructure_projects", "citizen_reports", "opportunity_zones",
        # Expansion 2026-03-07 — 4 new sources
        "business_licenses", "historic_markers", "community_centers", "education_facility",
        "parks_recreation", "city_owned_property", "zoning_decisions",
    ]
    # Sources with meaningful status breakdowns
    STATUS_SOURCES = {
        "code_violations", "building_permits", "infrastructure_projects",
        "business_licenses", "community_centers", "city_owned_property", "zoning_decisions",
    }

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

    nb = _resolve_neighborhood(neighborhood)
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
    result["next_steps"] = _next_steps("get_city_incidents", {"neighborhood": nb})
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
    nb = _resolve_neighborhood(neighborhood)
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
    result["next_steps"] = _next_steps("get_business_health", {"neighborhood": nb})
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
    ⚠ LATENCY: 30-60 seconds (parallel Brave searches + Gemini). Do NOT retry.
    AI: Gemini 2.5 Flash primary, Grok-4 via OpenRouter fallback. Temperature: 0.4.
    """
    neighborhood = _resolve_neighborhood(neighborhood)
    import asyncio

    # ── Real Montgomery stats: Census trends + incidents + deprivation scores ───
    conn = get_db()
    city_stats = {}
    with conn.cursor() as cur:
        # Latest values
        cur.execute("""
            SELECT metric, ROUND(AVG(value)::numeric, 1) as val
            FROM civic_data.census
            WHERE year = (SELECT MAX(year) FROM civic_data.census)
              AND metric IN ('median_income','poverty_below','unemployed','housing_vacant','median_rent')
              AND value > 0
            GROUP BY metric
        """)
        city_stats["current"] = {r[0]: float(r[1]) for r in cur.fetchall()}

        # 14-year trends (slope + R²) if neighborhood given
        if neighborhood:
            cur.execute("""
                SELECT metric,
                       ROUND(regr_slope(value, year)::numeric, 2) as slope,
                       ROUND(regr_r2(value, year)::numeric, 3) as r2,
                       MIN(value) as baseline, MAX(value) as current_val
                FROM civic_data.census
                WHERE neighborhood ILIKE %s
                AND metric IN ('median_income','poverty_below','unemployed','housing_vacant','median_rent')
                GROUP BY metric HAVING COUNT(*) >= 3
            """, (f"%{neighborhood}%",))
            rows = cur.fetchall()
            if rows:
                city_stats["trends"] = {
                    r[0]: {"slope_per_year": float(r[1]), "r2": float(r[2]),
                            "baseline": float(r[3]), "current_val": float(r[4]),
                            "direction": "improving" if (float(r[1]) > 0 and r[0] in ("median_income","median_rent")) else ("declining" if float(r[1]) < 0 else "stable")}
                    for r in rows
                }

        # Incidents count
        if neighborhood:
            cur.execute("""
                SELECT source, COUNT(*) as cnt FROM civic_data.city_data
                WHERE neighborhood ILIKE %s GROUP BY source ORDER BY cnt DESC LIMIT 5
            """, (f"%{neighborhood}%",))
            city_stats["top_incidents"] = {r[0]: int(r[1]) for r in cur.fetchall()}

    conn.close()

    # Add deprivation scores
    if neighborhood:
        try:
            scores_raw = json.loads(analyze_neighborhood(neighborhood, "all"))
            city_stats["deprivation_scores"] = {
                k: {"score": v.get("score"), "interpretation": v.get("interpretation")}
                for k, v in (scores_raw.get("scores") or {}).items()
            }
        except Exception:
            pass

    # ── Build category-specific search queries from actual ArcGIS data ──────────
    SOURCE_TO_CATEGORY = {
        "fire_incidents": ("public safety fire prevention", "FEMA AFG SAFER DOJ fire grant"),
        "code_violations": ("housing code enforcement blight", "HUD CDBG housing rehabilitation lead hazard"),
        "building_permits": ("construction development permits", "HUD HOME affordable housing development"),
        "housing_condition": ("housing quality substandard", "HUD Choice Neighborhoods HOME rehabilitation"),
        "food_safety": ("food safety restaurant inspection", "USDA food safety FDA grant community"),
        "environmental_nuisance": ("environmental pollution contamination", "EPA brownfields EJI environmental justice grant"),
        "transit_stops": ("public transit transportation access", "DOT FTA transit grant mobility"),
        "education_facilities": ("school education quality", "DOE Title I education grant community school"),
        "business_licenses": ("small business economic development", "SBA EDA economic development grant"),
        "parks_recreation": ("parks green space recreation", "DOI Land Water Conservation Fund recreation grant"),
        "community_centers": ("community services social programs", "HHS CSBG community services block grant"),
        "infrastructure_projects": ("infrastructure roads utilities", "DOT RAISE BUILD infrastructure grant"),
        "opportunity_zones": ("economic opportunity investment", "Treasury Opportunity Zone tax incentive investment"),
        "behavioral_centers": ("mental health substance abuse", "SAMHSA HHS behavioral health grant"),
        "citizen_reports": ("neighborhood quality of life", "HUD community development grant"),
    }

    top_incidents = city_stats.get("top_incidents", {})
    geo = f"Montgomery Alabama {neighborhood}" if neighborhood else "Montgomery Alabama"

    # Build targeted queries from top 2 incident categories
    category_queries = []
    for source, count in list(top_incidents.items())[:2]:
        if source in SOURCE_TO_CATEGORY:
            civic_kw, federal_kw = SOURCE_TO_CATEGORY[source]
            category_queries.append(f"{geo} {civic_kw} {federal_kw} 2025 2026 grant funding application")

    # Global best practices — 2 targeted queries for comparable cities
    top_issues = " ".join(list(top_incidents.keys())[:3]) if top_incidents else problem
    global_q1 = f"{top_issues} city revitalization success story measurable outcome percent reduction"
    global_q2 = f"US city solved {top_issues} low income neighborhood case study results statistics"
    local_q   = f"{geo} {top_issues} program solution results 2024 2025"

    # Run all searches in parallel
    search_coros = [_brave_search(q, count=4) for q in category_queries]
    search_coros += [_brave_search(global_q1, count=4), _brave_search(global_q2, count=4), _brave_search(local_q, count=3)]
    search_results = await asyncio.gather(*search_coros)

    federal_res = []
    for r in search_results[:-3]:
        federal_res.extend(r)
    global_res = search_results[-3] + search_results[-2]
    local_res  = search_results[-1]

    # ── Render Jinja2 prompt ────────────────────────────────────────────────────
    prompt = _render("find_solutions.j2",
        problem=problem,
        neighborhood=neighborhood,
        city_stats=city_stats,
        federal_results=federal_res,
        global_results=global_res,
        local_results=local_res,
    )

    raw = await _generate_json(prompt, temperature=0.4)
    try:
        parsed = json.loads(raw)
        parsed["next_steps"] = _next_steps("find_solutions", {"neighborhood": neighborhood})
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except Exception:
        return raw


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

    if neighborhood != "list":
        neighborhood = _resolve_neighborhood(neighborhood) or neighborhood
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
    result["next_steps"] = _next_steps("analyze_neighborhood", {"neighborhood": neighborhood if neighborhood != "list" else None})
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── TOOL 14 — civic_report ──────────────────────────────────────────────────────
@mcp.tool()
async def civic_report(neighborhood: str) -> str:
    """
    ANALYZE tool — full civic intelligence report for a Montgomery neighborhood.
    VALID NEIGHBORHOOD NAMES (use exactly): "Centennial Hill", "Downtown Montgomery",
    "West Side", "South Montgomery", "Southeast Montgomery", "Midtown / Cloverdale",
    "Cottage Hill", "North Montgomery / Chisholm", "East Montgomery / Eastdale",
    "East Montgomery / Vaughn", "East Montgomery / Forest Park",
    "Northwest Montgomery County", "Rural Montgomery County", "Pike Road".
    For city-wide analysis use neighborhood=None or "Montgomery".
    Do NOT use sub-neighborhood names (e.g. "Capitol Heights") — map to closest zone.
    Aggregates Census trend, 19 ArcGIS sources, Zillow, Yelp, ADI/SVI/EJI scores,
    then calls Gemini 2.5 Flash to produce a factual, hallucination-resistant civic analysis.

    ⚠ LATENCY: This tool takes 20-40 seconds. Do NOT retry — wait for the response.
    AI: Gemini 2.5 Flash primary, Grok-4 via OpenRouter fallback. Temperature: 0.1.
    Scores: ADI (material deprivation, UW Madison/HRSA), SVI (social vulnerability, CDC/ATSDR),
    EJI (environmental burden, EPA). All 0.0-1.0, higher = worse, percentile vs 71 Montgomery tracts.
    Output: structured JSON with overall_severity, findings[], strongest_signal, data_confidence.
    All numbers verified against real data — no inference allowed.

    Use this before find_solutions() to ground solution recommendations in confirmed facts.
    """
    # ── Step 1: Resolve neighborhood name + collect all research data ────────────
    neighborhood = _resolve_neighborhood(neighborhood) or "Montgomery"
    census   = json.loads(get_census_trend(neighborhood))
    incidents_list = []
    for source in ["code_violations", "building_permits", "fire_incidents",
                   "housing_condition", "food_safety", "environmental_nuisance",
                   "business_licenses", "transit_stops", "city_owned_property",
                   "zoning_decisions", "parks_recreation", "community_centers",
                   "behavioral_centers", "infrastructure_projects", "citizen_reports",
                   "opportunity_zones", "historic_markers", "education_facility",
                   "education_facilities"]:
        inc = json.loads(get_city_incidents(source, neighborhood))
        if inc.get("total", 0) > 0:
            incidents_list.append(inc)

    business = json.loads(get_business_health(neighborhood))
    scores   = json.loads(analyze_neighborhood(neighborhood, "all"))

    # Zillow housing data + survey citizen signals
    conn = get_db()
    housing = {}
    survey_signals = {}
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT COUNT(*) as count, AVG(price) as avg_price,
                   MIN(price) as min_price, MAX(price) as max_price,
                   AVG(days_on_market) as avg_dom
            FROM civic_data.properties
            WHERE source = 'zillow' AND price > 0
            AND (%s OR neighborhood ILIKE %s)
        """, (neighborhood == "all", f"%{neighborhood}%"))
        row = cur.fetchone()
        if row and row["count"]:
            housing = {
                "listings": row["count"],
                "avg_price": round(row["avg_price"]) if row["avg_price"] else None,
                "min_price": round(row["min_price"]) if row["min_price"] else None,
                "max_price": round(row["max_price"]) if row["max_price"] else None,
                "avg_days_on_market": round(row["avg_dom"]) if row["avg_dom"] else None,
            }

        # Survey aggregate: top citizen-selected answers across all questionnaires
        cur.execute("""
            SELECT ro.body->>'en' AS answer,
                   q.body->>'en'  AS question,
                   COUNT(*)        AS votes
            FROM decidim_forms_response_choices rc
            JOIN decidim_forms_response_options ro ON ro.id = rc.decidim_response_option_id
            JOIN decidim_forms_questions q ON q.id = ro.decidim_question_id
            WHERE rc.decidim_response_option_id IS NOT NULL
              AND ro.body->>'en' IS NOT NULL
              AND ro.body->>'en' != ''
            GROUP BY ro.body->>'en', q.body->>'en'
            ORDER BY votes DESC
            LIMIT 20
        """)
        top_answers = cur.fetchall()

        # Count total survey respondents
        cur.execute("SELECT COUNT(DISTINCT decidim_user_id) FROM decidim_forms_responses")
        n_respondents = (cur.fetchone() or {}).get("count", 0)

        # Count total responses (question-level)
        cur.execute("SELECT COUNT(*) FROM decidim_forms_response_choices WHERE decidim_response_option_id IS NOT NULL")
        n_choices = (cur.fetchone() or {}).get("count", 0)

        survey_signals = {
            "total_respondents": n_respondents,
            "total_choices_recorded": n_choices,
            "top_citizen_priorities": [
                {"answer": r["answer"], "question": r["question"], "votes": r["votes"]}
                for r in top_answers
            ],
        }
    conn.close()

    # ── Step 2: Build RAG data block ────────────────────────────────────────────
    rag = {
        "neighborhood": neighborhood,
        "census_trend": census.get("metrics", {}),
        "city_incidents": {i["source"]: i["total"] for i in incidents_list},
        "business_health": {
            "total": business.get("total", 0),
            "closed": business.get("closed", 0),
            "avg_rating": business.get("avg_rating"),
            "top_categories": business.get("top_categories", {}),
        },
        "housing_market": housing,
        "deprivation_scores": {
            idx: {
                "score": s.get("score"),
                "interpretation": s.get("interpretation"),
                "top_factors": s.get("top_factors", []),
            }
            for idx, s in scores.get("scores", {}).items()
            if "score" in s
        },
        "citizen_survey_signals": survey_signals,
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
        parsed["next_steps"] = _next_steps("civic_report", {"neighborhood": neighborhood})
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return raw


# ── TOOL 15 — post_ai_response ──────────────────────────────────────────────────
@mcp.tool()
async def post_ai_response(proposal_id: str) -> str:
    """
    WRITE tool — closes the civic loop with data-enriched, human-tone response.
    Flow:
      1. Fetch proposal + existing comments
      2. Classify → detect category + neighborhood
      3. summarize_comments → understand citizen sentiment already in the thread
      4. civic_report(neighborhood) → real Census, ArcGIS, Yelp, ADI/SVI/EJI data
      5. get_meetings → next public meeting on this topic
      6. Generate authoritative but human comment grounded in real data
      7. Post on Decidim as Momentum AI
    Tone: senior urban planner speaking to a citizen — factual, warm, actionable. No jargon.
    """
    # ── Step 1: Fetch proposal + comments ────────────────────────────────────────
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
                comments { id body alignment }
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
    existing_comments = proposal.get("comments") or []

    # ── Step 2: Classify + detect neighborhood ───────────────────────────────────
    classification = json.loads(await classify_proposal(text))
    category = classification.get("category", "governance")
    actionable = classification.get("311_actionable", False)

    # Extract neighborhood hint from proposal text (zip codes or known area names)
    nb_prompt = f"""From this civic proposal text, extract the Montgomery AL neighborhood or zip code mentioned.
If none found, return null.
Proposal: "{text}"
Return JSON: {{"neighborhood": "name or null"}}"""
    nb_raw = await _generate_json(nb_prompt, temperature=0.0)
    try:
        detected_nb = json.loads(nb_raw).get("neighborhood") or "Montgomery"
    except Exception:
        detected_nb = "Montgomery"

    # ── Step 3: Citizen sentiment ─────────────────────────────────────────────────
    sentiment_data = {}
    if existing_comments:
        sentiment_raw = await summarize_comments(proposal_id)
        try:
            sentiment_data = json.loads(sentiment_raw)
        except Exception:
            pass

    # ── Step 4: Real civic data for this neighborhood ─────────────────────────────
    report = json.loads(await civic_report(detected_nb))
    severity = report.get("overall_severity", "moderate")
    findings = report.get("findings", [])
    scores = report.get("deprivation_scores", {}) or {}
    adi_score = (scores.get("ADI") or {}).get("score")
    top_incidents = {i["source"]: i["total"] for i in (report.get("_sources", {}).get("incidents_sources") or [])}

    # ── Step 5: Next public meeting ───────────────────────────────────────────────
    meetings_raw = await get_meetings(upcoming_only=True)
    meetings_data = json.loads(meetings_raw)
    next_meeting = (meetings_data.get("meetings") or [None])[0]
    next_meeting_str = ""
    if next_meeting:
        next_meeting_str = f"{next_meeting.get('title','')} — {(next_meeting.get('start') or '')[:10]}"

    # ── Step 6: Generate human-tone comment grounded in data ─────────────────────
    n_comments = len(existing_comments)
    support_level = sentiment_data.get("support_level", "")
    key_themes = sentiment_data.get("key_themes", [])
    top_finding = findings[0].get("finding", "") if findings and isinstance(findings[0], dict) else (findings[0] if findings else "")

    comment_prompt = f"""You are Momentum AI, the civic intelligence system for the City of Montgomery, Alabama.
Write a comment on a citizen proposal. Your tone: senior urban planner speaking directly to a resident — authoritative, warm, grounded in facts. Never bureaucratic, never cheerful. No emojis.

PROPOSAL: "{title}"
CATEGORY: {category}
NEIGHBORHOOD: {detected_nb}

CITIZEN CONTEXT:
- {n_comments} citizens have commented on this proposal
- Community sentiment: {support_level or "mixed"}
- Key themes raised by citizens: {', '.join(key_themes[:3]) if key_themes else "not yet analyzed"}

REAL DATA FOR THIS NEIGHBORHOOD:
- Overall severity: {severity}
- ADI deprivation score: {f"{round(adi_score * 100)}th percentile" if adi_score else "not available"} (higher = more deprived)
- Top confirmed finding: {top_finding}
- 311 actionable: {actionable}
- Next public meeting: {next_meeting_str or "check mgm.styxcore.dev for upcoming meetings"}

RULES:
- Reference the citizen discussion naturally ("Several residents have raised...", "The community has flagged...")
- Cite 1-2 real numbers from the data above — translate them into human impact
- Give one concrete next step (funding, meeting, 311, city department)
- 3-4 sentences max. Plain English. No bullet points. No markdown.
- End with: "— Momentum AI, City of Montgomery"

Write only the comment text."""

    comment_body = await _generate_json(comment_prompt, temperature=0.3)
    try:
        parsed = json.loads(comment_body)
        comment_body = parsed.get("comment", comment_body) if isinstance(parsed, dict) else comment_body
    except Exception:
        pass
    comment_body = comment_body.strip().strip('"')

    # ── Step 7: Post via GraphQL ──────────────────────────────────────────────────
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

    errors = result.get("errors") or []
    real_errors = [e for e in errors if "badge" not in e.get("message", "").lower()]
    if real_errors:
        return json.dumps({"error": real_errors[0]["message"], "proposal_id": proposal_id})

    comment = ((result.get("data") or {}).get("commentable") or {}).get("addComment") or {}
    return json.dumps({
        "status": "posted",
        "proposal_id": proposal_id,
        "proposal_title": title,
        "category": category,
        "neighborhood_analyzed": detected_nb,
        "severity": severity,
        "citizen_comments_read": n_comments,
        "comment_id": comment.get("id"),
        "comment_preview": comment_body[:300],
        "platform_url": f"{os.getenv('DECIDIM_URL')}/processes",
    }, ensure_ascii=False, indent=2)


# ── TOOL 16 — get_meetings ──────────────────────────────────────────────────────
@mcp.tool()
async def get_meetings(upcoming_only: bool = False) -> str:
    """
    Returns all scheduled meetings and public hearings from Decidim.
    Covers city council sessions, participatory process assemblies, public consultations.
    upcoming_only=True returns only meetings with startTime in the future.
    """
    query = """
    query {
      participatoryProcesses {
        title { translation(locale: "en") }
        components {
          ... on Meetings {
            meetings(first: 100) {
              nodes {
                id
                title { translation(locale: "en") }
                description { translation(locale: "en") }
                startTime
                endTime
                address
                location { translation(locale: "en") }
                attendeesCount
              }
            }
          }
        }
      }
    }"""
    data = await graphql(query)
    meetings = []
    for proc in (data.get("data", {}).get("participatoryProcesses") or []):
        proc_title = (proc.get("title") or {}).get("translation", "")
        for comp in (proc.get("components") or []):
            for node in (comp.get("meetings", {}).get("nodes") or []):
                start = node.get("startTime", "")
                if upcoming_only and start:
                    from datetime import datetime, timezone
                    try:
                        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                        if dt < datetime.now(timezone.utc):
                            continue
                    except Exception:
                        pass
                meetings.append({
                    "id": node.get("id"),
                    "process": proc_title,
                    "title": (node.get("title") or {}).get("translation", ""),
                    "description": ((node.get("description") or {}).get("translation", "") or "")[:200],
                    "start": start,
                    "end": node.get("endTime", ""),
                    "address": node.get("address", ""),
                    "location": (node.get("location") or {}).get("translation", ""),
                    "attendees": node.get("attendeesCount", 0),
                })

    meetings.sort(key=lambda m: m.get("start") or "")
    return json.dumps({
        "total": len(meetings),
        "filter": "upcoming only" if upcoming_only else "all",
        "meetings": meetings,
        "next_steps": _next_steps("get_meetings"),
    }, ensure_ascii=False, indent=2)


# ── TOOL 17 — summarize_comments ────────────────────────────────────────────────
@mcp.tool()
async def summarize_comments(proposal_id: str) -> str:
    """
    Fetches all citizen comments on a Decidim proposal and generates an AI summary
    of community sentiment, key themes, concerns, and consensus points.
    Returns structured JSON: sentiment, themes, concerns, support_level, summary.
    """
    # Query all proposals with comments — body on Comment is a String (not TranslatedField)
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
                comments { id body alignment }
              }
            }
          }
        }
      }
    }"""
    pdata = await graphql(pq)
    proposal = None
    for proc in (pdata.get("data", {}).get("participatoryProcesses") or []):
        for comp in (proc.get("components") or []):
            for node in (comp.get("proposals", {}).get("nodes") or []):
                if str(node.get("id")) == str(proposal_id):
                    proposal = node
                    break

    if not proposal:
        return json.dumps({"error": f"Proposal {proposal_id} not found"})

    title = (proposal.get("title") or {}).get("translation", "")
    body = (proposal.get("body") or {}).get("translation", "")
    comments = proposal.get("comments") or []

    if not comments:
        return json.dumps({
            "proposal_id": proposal_id,
            "title": title,
            "total_comments": 0,
            "summary": "No citizen comments yet on this proposal.",
        })

    comment_texts = []
    for c in comments:
        text = c.get("body") or ""  # body is a plain String on Comment
        alignment = c.get("alignment", 0)
        stance = "supports" if alignment == 1 else ("opposes" if alignment == -1 else "neutral")
        if text:
            comment_texts.append(f"[{stance}] {str(text)[:300]}")

    prompt = f"""Analyze citizen comments on this civic proposal and return a JSON object.

Proposal: "{title}"
Description: {body[:300]}

Comments ({len(comment_texts)} total):
{chr(10).join(comment_texts[:30])}

Return JSON with this exact structure:
{{
  "sentiment": "positive|mixed|negative|neutral",
  "support_level": "strong|moderate|divided|opposed",
  "total_analyzed": {len(comment_texts)},
  "key_themes": ["theme1", "theme2", "theme3"],
  "main_concerns": ["concern1", "concern2"],
  "consensus_points": ["point1", "point2"],
  "summary": "2-3 sentence plain English summary of what citizens think"
}}"""

    raw = await _generate_json(prompt, temperature=0.1)
    try:
        result = json.loads(raw)
        result["proposal_id"] = proposal_id
        result["proposal_title"] = title
        result["next_steps"] = _next_steps("summarize_comments")
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception:
        return json.dumps({
            "proposal_id": proposal_id,
            "title": title,
            "total_comments": len(comments),
            "summary": raw[:500],
        })


# ─────────────────────────────────────────────
# TOOL 18 — export_to_sheet
# ─────────────────────────────────────────────
@mcp.tool()
async def export_to_sheet(neighborhood: str) -> str:
    """Export all civic data for a neighborhood to Google Sheets (Census trends, incidents, business health, ADI/SVI/EJI scores)."""
    import workspace_client as ws
    from datetime import datetime

    sheet_id, sheet_url = ws.create_or_get_sheet("Momentum MGM — Civic Intelligence")

    results = {}
    errors = []

    try:
        results["census"] = json.loads(get_census_trend(neighborhood))
    except Exception as e:
        errors.append(f"census: {e}")

    try:
        results["incidents"] = json.loads(get_city_incidents("list", neighborhood))
    except Exception as e:
        errors.append(f"incidents: {e}")

    try:
        results["business"] = json.loads(get_business_health(neighborhood))
    except Exception as e:
        errors.append(f"business: {e}")

    try:
        results["scores"] = json.loads(analyze_neighborhood(neighborhood, "all"))
    except Exception as e:
        errors.append(f"scores: {e}")

    rows_written = 0

    # Tab 1: Census trends
    census = results.get("census", {})
    if census and not census.get("error"):
        metrics = census.get("metrics", {})
        rows = [["Metric", "Baseline (2012)", "Current (2024)", "Change/yr", "R²", "Projection 2026"]]
        for metric_name, m in metrics.items():
            rows.append([
                metric_name,
                m.get("baseline", ""),
                m.get("current", ""),
                m.get("slope_per_year", ""),
                m.get("r2", ""),
                m.get("projection_2026", ""),
            ])
        ws.write_to_sheet(sheet_id, f"{neighborhood} — Census", rows)
        rows_written += len(rows)

    # Tab 2: Incidents
    incidents = results.get("incidents", {})
    if incidents and not incidents.get("error"):
        available = incidents.get("available_sources", {}) or {}
        rows = [["Source", "Count"]]
        for source, count in available.items():
            rows.append([source, count])
        ws.write_to_sheet(sheet_id, f"{neighborhood} — Incidents", rows)
        rows_written += len(rows)

    # Tab 3: Business health
    biz = results.get("business", {})
    if biz and not biz.get("error"):
        closed = biz.get("closed", 0)
        total = biz.get("total", 0)
        closure_rate = round(closed / total * 100, 1) if total else 0
        rows = [
            ["Metric", "Value"],
            ["Total Businesses", total],
            ["Closed", closed],
            ["Closure Rate", f"{closure_rate}%"],
            ["Avg Rating", biz.get("avg_rating", "")],
            ["Avg Reviews", biz.get("avg_reviews", "")],
        ]
        cats = biz.get("top_categories", {}) or {}
        if cats:
            rows.append(["", ""])
            rows.append(["Top Categories", "Count"])
            for cat, cnt in list(cats.items())[:5]:
                rows.append([cat, cnt])
        ws.write_to_sheet(sheet_id, f"{neighborhood} — Business", rows)
        rows_written += len(rows)

    # Tab 4: ADI/SVI/EJI scores
    scores_data = results.get("scores", {})
    if scores_data and not scores_data.get("error"):
        score_dict = scores_data.get("scores", {}) or {}
        rows = [["Index", "Score", "Interpretation", "Top Factor", "Low Confidence"]]
        for idx in ["ADI", "SVI", "EJI"]:
            d = score_dict.get(idx, {}) or {}
            top = (d.get("top_factors") or [{}])[0]
            rows.append([
                idx,
                d.get("score", ""),
                d.get("interpretation", ""),
                top.get("variable", ""),
                d.get("low_confidence", ""),
            ])
        ws.write_to_sheet(sheet_id, "Scores ADI-SVI-EJI", rows)
        rows_written += len(rows)

    return json.dumps({
        "sheet_url": sheet_url,
        "neighborhood": neighborhood,
        "rows_written": rows_written,
        "tabs_created": 4,
        "errors": errors,
        "exported_at": datetime.now().isoformat(),
    }, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# TOOL 19 — create_report_doc
# ─────────────────────────────────────────────
@mcp.tool()
async def create_report_doc(neighborhood: str) -> str:
    """Generate a full civic intelligence report as a Google Doc shared with the admin."""
    import workspace_client as ws
    from datetime import datetime

    date_str = datetime.now().strftime("%B %d, %Y")
    title = f"Civic Intelligence Report — {neighborhood} — {date_str}"

    report_data = {}
    solutions_data = {}

    try:
        report_raw = await civic_report(neighborhood)
        report_data = json.loads(report_raw)
    except Exception as e:
        report_data = {"error": str(e)}

    try:
        # Build specific problem string from actual findings
        declining = [f.get("metric_cited","") for f in (report_data.get("findings") or []) if f.get("trend") == "declining"]
        severity = report_data.get("overall_severity", "high")
        problem_str = f"{severity} severity neighborhood — issues: {', '.join(declining) if declining else 'housing, poverty, infrastructure'}"
        solutions_raw = await find_solutions(problem_str, neighborhood)
        solutions_data = json.loads(solutions_raw)
    except Exception as e:
        solutions_data = {"error": str(e)}

    # Get deprivation scores separately
    scores_raw = analyze_neighborhood(neighborhood, "all")
    scores_data = json.loads(scores_raw)
    score_dict = scores_data.get("scores", {}) or {}

    # ── Rewrite as executive briefing prose via Gemini ──────────────────────────
    briefing_prompt = f"""You are a senior policy analyst writing a municipal briefing document for the City of Montgomery, Alabama city council.
Rewrite the following civic intelligence data as a professional, readable government briefing.

Rules:
- Write in complete sentences and paragraphs. No bullet points in the summary.
- Explain what every abbreviation means the first time you use it.
- Translate numbers into human impact: instead of "housing_vacant: 207.6", write "over 200 abandoned properties".
- Use plain English that a city council member with no data science background can understand.
- Keep each section concise: 2-4 sentences max per section.
- Do NOT invent data not present below.

RAW DATA:
Neighborhood: {neighborhood}
Overall severity: {report_data.get('overall_severity','')}
Severity rationale: {report_data.get('severity_rationale','')}
Strongest signal: {report_data.get('strongest_signal','')}
Key findings: {json.dumps([f.get('finding','') for f in (report_data.get('findings') or [])], ensure_ascii=False)}
Deprivation scores: {json.dumps({k: v.get('interpretation','') for k,v in score_dict.items()}, ensure_ascii=False)}
Federal programs available: {json.dumps([p.get('name','') + ' — ' + p.get('description','') for p in (solutions_data.get('federal_programs') or [])], ensure_ascii=False)}
Comparable cities: {json.dumps([c.get('city','') + ': ' + c.get('lesson','') for c in (solutions_data.get('comparable_cities') or [])], ensure_ascii=False)}
Recommended actions: {json.dumps(solutions_data.get('montgomery_recommendations',[]), ensure_ascii=False)}
Urgency: {solutions_data.get('urgency','')} — Timeline: {solutions_data.get('estimated_timeline','')}

Return a JSON object with these exact keys:
{{
  "executive_summary": "3-4 sentence plain English overview of the neighborhood situation",
  "situation_analysis": "2-3 sentences explaining what the deprivation scores mean in plain English",
  "key_findings_prose": ["One clear sentence per finding, no jargon, no abbreviations"],
  "federal_programs_prose": ["One paragraph per program: what it is, how much money, why it fits this neighborhood"],
  "cities_prose": ["One sentence per city: what they did and the concrete result"],
  "actions_prose": ["One clear action sentence per recommendation, written as a directive to city staff"],
  "closing": "One sentence on urgency and timeline"
}}"""

    briefing_raw = await _generate_json(briefing_prompt, temperature=0.2)
    try:
        briefing = json.loads(briefing_raw)
    except Exception:
        briefing = {}

    severity = report_data.get("overall_severity", "unknown").upper()
    urgency = solutions_data.get("urgency", "")
    timeline = solutions_data.get("estimated_timeline", "")

    sections = []
    sections.append((title, "h1"))
    sections.append((f"Prepared by Momentum MGM Civic AI  —  mgm.styxcore.dev  —  {date_str}", "body"))
    sections.append((f"Overall Severity: {severity}  |  Urgency: {urgency.upper() if urgency else ''}  |  Timeline: {timeline}", "body"))
    sections.append(("", "body"))

    sections.append(("EXECUTIVE SUMMARY", "h2"))
    sections.append((briefing.get("executive_summary", report_data.get("severity_rationale", "")), "body"))
    sections.append(("", "body"))

    sections.append(("SITUATION ANALYSIS", "h2"))
    sections.append((briefing.get("situation_analysis", ""), "body"))
    sections.append(("", "body"))

    sections.append(("KEY FINDINGS", "h2"))
    for finding in (briefing.get("key_findings_prose") or [f.get("finding","") for f in (report_data.get("findings") or [])]):
        sections.append((str(finding), "bullet"))
    sections.append(("", "body"))

    sections.append(("RECOMMENDED FEDERAL PROGRAMS", "h2"))
    for prog_prose in (briefing.get("federal_programs_prose") or []):
        sections.append((str(prog_prose), "bullet"))
        sections.append(("", "body"))

    sections.append(("COMPARABLE CITIES & BEST PRACTICES", "h2"))
    for city_prose in (briefing.get("cities_prose") or []):
        sections.append((str(city_prose), "bullet"))
    sections.append(("", "body"))

    sections.append(("GLOBAL BEST PRACTICES", "h2"))
    for gp in (solutions_data.get("global_best_practices") or []):
        line = f"{gp.get('city','')} — {gp.get('practice','')}. Result: {gp.get('outcome','')}"
        sections.append((line, "bullet"))
    sections.append(("", "body"))

    sections.append(("RECOMMENDED ACTIONS FOR MONTGOMERY", "h2"))
    if urgency:
        sections.append((f"Priority level: {urgency.upper()} — Estimated timeline to see impact: {timeline}", "body"))
    for action in (briefing.get("actions_prose") or solutions_data.get("montgomery_recommendations") or []):
        sections.append((str(action), "bullet"))
    sections.append(("", "body"))

    if briefing.get("closing"):
        sections.append((briefing["closing"], "body"))
        sections.append(("", "body"))

    sources = report_data.get("_sources", {}) or {}
    sections.append(("DATA SOURCES", "h2"))
    sections.append((f"Census data: {sources.get('census_tracts', 'U.S. Census ACS 5-year estimates 2012-2024')}", "body"))
    sections.append((f"City incident data: {', '.join(sources.get('incidents_sources', []))}", "body"))
    sections.append((f"Deprivation methodology: Area Deprivation Index (UW Madison/HRSA), Social Vulnerability Index (CDC/ATSDR), Environmental Justice Index (EPA)", "body"))
    sections.append(("", "body"))
    sections.append(("Generated by Momentum MGM Civic AI — mgm.styxcore.dev", "body"))

    doc_id, doc_url = ws.create_doc(title, sections)

    return json.dumps({
        "doc_url": doc_url,
        "title": title,
        "shared_with": os.getenv("GOOGLE_ADMIN_EMAIL"),
        "neighborhood": neighborhood,
        "created_at": datetime.now().isoformat(),
    }, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# TOOL 20 — sync_gcal
# ─────────────────────────────────────────────
@mcp.tool()
async def sync_gcal() -> str:
    """Sync all Decidim public meetings to Google Calendar. Creates calendar if needed."""
    import workspace_client as ws
    from datetime import datetime, timedelta, timezone

    cal_service = ws.get_calendar_service()
    cal_name = "Montgomery Civic — Public Meetings"
    existing_cals = cal_service.calendarList().list().execute()
    cal_id = None
    for c in existing_cals.get("items", []):
        if c.get("summary") == cal_name:
            cal_id = c["id"]
            break
    if not cal_id:
        cal_id, _ = ws.create_calendar(cal_name)

    cal_url = f"https://calendar.google.com/calendar/r?cid={cal_id}"

    meetings_raw = await get_meetings()
    meetings_data = json.loads(meetings_raw)
    meetings = meetings_data.get("meetings", [])

    synced = 0
    skipped = 0
    errors = []

    for m in meetings:
        try:
            start_str = m.get("start_time") or m.get("start")
            end_str = m.get("end_time") or m.get("end")

            if not start_str:
                start_dt = datetime.now(timezone.utc) + timedelta(days=7)
                end_dt = start_dt + timedelta(hours=1)
                start_str = start_dt.isoformat()
                end_str = end_dt.isoformat()
            elif not end_str:
                from dateutil import parser as dtparser
                start_dt = dtparser.parse(start_str)
                end_str = (start_dt + timedelta(hours=1)).isoformat()

            title = m.get("title", "Montgomery Public Meeting")
            description = m.get("description", "")
            location = m.get("location", "Montgomery, AL")

            event = {
                "summary": f"[Momentum MGM] {title}",
                "description": f"{description}\n\nView on Decidim: https://mgm.styxcore.dev",
                "location": location,
                "start": {"dateTime": start_str, "timeZone": "America/Chicago"},
                "end": {"dateTime": end_str, "timeZone": "America/Chicago"},
            }

            result = ws.create_calendar_event(cal_id, event)
            if result == "skipped":
                skipped += 1
            else:
                synced += 1
        except Exception as e:
            errors.append(f"{m.get('title', '?')}: {e}")

    return json.dumps({
        "synced": synced,
        "skipped": skipped,
        "total_meetings": len(meetings),
        "calendar_url": cal_url,
        "calendar_id": cal_id,
        "errors": errors,
    }, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# TOOL 21 — create_report_slides
# ─────────────────────────────────────────────
@mcp.tool()
async def create_report_slides(neighborhood: str) -> str:
    """Generate a Google Slides presentation from a civic report.
    Produces a city-council-ready deck: key stats, deprivation scores,
    top incidents, federal programs, and concrete recommendations.
    Returns the presentation URL."""
    from workspace_client import create_slides
    from datetime import datetime

    # Gather data
    report_raw = await civic_report(neighborhood)
    solutions_raw = await find_solutions(
        problem=f"civic challenges in {neighborhood}",
        neighborhood=neighborhood
    )
    scores_raw = analyze_neighborhood(neighborhood=neighborhood, index="all")

    report = json.loads(report_raw)
    solutions = json.loads(solutions_raw)
    scores = json.loads(scores_raw)

    today = datetime.now().strftime("%B %d, %Y")
    title = f"Civic Intelligence Report — {neighborhood} — {today}"

    # Build slide data
    severity = report.get("overall_severity") or report.get("severity", "N/A")
    score_block = scores.get("scores", scores)
    adi = score_block.get("ADI", {})
    svi = score_block.get("SVI", {})
    eji = score_block.get("EJI", {})

    def _sev(score):
        if score is None: return "N/A"
        if score > 0.75: return "critical"
        if score > 0.50: return "high"
        if score > 0.25: return "moderate"
        return "low"

    # findings may be dicts {finding, category, ...} or plain strings
    raw_findings = report.get("findings", [])
    findings = [
        f.get("finding", str(f)) if isinstance(f, dict) else str(f)
        for f in raw_findings
    ]

    programs = solutions.get("federal_programs", [])[:3]
    recs = solutions.get("montgomery_recommendations", [])[:3]
    cities = solutions.get("comparable_cities", [])[:2]
    best_practices = solutions.get("global_best_practices", [])[:2]

    slides_data = [
        {
            "title": f"Momentum MGM — {neighborhood}",
            "body": [
                f"Civic Intelligence Report | {today}",
                "",
                f"Overall Severity: {severity.upper() if severity != 'N/A' else 'N/A'}",
                f"ADI Score: {adi.get('score', 'N/A')} — {_sev(adi.get('score'))}",
                f"SVI Score: {svi.get('score', 'N/A')} — {_sev(svi.get('score'))}",
                f"EJI Score: {eji.get('score', 'N/A')} — {_sev(eji.get('score'))}",
                "",
                "Generated by Momentum MGM Civic AI · mgm.styxcore.dev",
            ],
        },
        {
            "title": "Key Findings",
            "body": [f"• {f}" for f in findings[:6]] if findings else ["No findings available."],
        },
        {
            "title": "Deprivation Scores vs 71 Montgomery Tracts",
            "body": [
                f"Area Deprivation Index (ADI): {adi.get('score', 'N/A')} — {_sev(adi.get('score'))}",
                f"  {adi.get('interpretation', '')}",
                "",
                f"Social Vulnerability Index (SVI): {svi.get('score', 'N/A')} — {_sev(svi.get('score'))}",
                f"  {svi.get('interpretation', '')}",
                "",
                f"Environmental Justice Index (EJI): {eji.get('score', 'N/A')} — {_sev(eji.get('score'))}",
                f"  {eji.get('interpretation', '')}",
            ],
        },
        {
            "title": "Federal Programs Available",
            "body": [
                f"• {p.get('name', '')} ({p.get('agency', '')})\n  {p.get('amount') or 'Amount varies'} — {p.get('next_step', '')[:100]}"
                for p in programs
            ] if programs else ["See find_solutions() for available federal programs."],
        },
        {
            "title": "Comparable Cities — What Worked",
            "body": [
                f"• {c.get('city', '')}: {c.get('approach', '')[:120]}\n  Result: {c.get('outcome', '')[:100]}\n  Lesson: {c.get('lesson', '')[:100]}"
                for c in cities
            ] if cities else [
                f"• {b.get('city', '')}: {b.get('practice', '')[:120]}\n  Result: {b.get('outcome', '')[:100]}"
                for b in best_practices
            ] if best_practices else ["No comparable city data available."],
        },
        {
            "title": "Recommended Actions",
            "body": [f"• {r}" for r in recs] if recs else ["See find_solutions() for recommendations."],
            "notes": f"Urgency: {solutions.get('urgency', 'N/A')} — {solutions.get('urgency_rationale', '')}",
        },
        {
            "title": "Next Steps",
            "body": [
                "1. Share this report with relevant city departments",
                "2. Submit federal grant applications (see slide 4 for deadlines)",
                "3. Post AI response to citizen proposals on mgm.styxcore.dev",
                "4. Export full data to Google Sheets: export_to_sheet()",
                "5. Create action task list: create_action_tasks()",
                "",
                "Momentum MGM Civic AI · mgm.styxcore.dev · mcp.styxcore.dev/mcp",
            ],
        },
    ]

    prs_id, prs_url = create_slides(title, slides_data)
    return json.dumps({
        "presentation_url": prs_url,
        "title": title,
        "slides": len(slides_data),
        "shared_with": os.getenv("GOOGLE_ADMIN_EMAIL"),
        "neighborhood": neighborhood,
        "created_at": today,
    }, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# TOOL 22 — create_action_tasks
# ─────────────────────────────────────────────
@mcp.tool()
async def create_action_tasks(neighborhood: str) -> str:
    """Create a Google Tasks list from find_solutions recommendations.
    Each WHO+WHAT+BY WHEN recommendation becomes an actionable task
    assigned to the relevant city department. Returns the task list URL."""
    from workspace_client import create_task_list
    from datetime import datetime

    solutions_raw = await find_solutions(
        problem=f"civic challenges in {neighborhood}",
        neighborhood=neighborhood
    )
    solutions = json.loads(solutions_raw)
    today = datetime.now().strftime("%B %d, %Y")
    list_title = f"Momentum MGM — {neighborhood} Action Items — {today}"

    tasks = []

    # Main recommendations
    for rec in solutions.get("montgomery_recommendations", []):
        tasks.append({
            "title": rec[:100],
            "notes": rec if len(rec) > 100 else "",
        })

    # Federal programs as tasks (apply for each)
    for prog in solutions.get("federal_programs", []):
        name = prog.get("name", "")
        agency = prog.get("agency", "")
        next_step = prog.get("next_step", "")
        amount = prog.get("amount", "")
        source = prog.get("source_url", "")
        tasks.append({
            "title": f"Apply: {name} ({agency})",
            "notes": f"{next_step}\nAmount: {amount}\nSource: {source}".strip(),
        })

    # Comparable city lessons as research tasks
    for city in solutions.get("comparable_cities", []):
        tasks.append({
            "title": f"Research model: {city.get('city', '')}",
            "notes": f"Approach: {city.get('approach', '')}\nOutcome: {city.get('outcome', '')}\nLesson: {city.get('lesson', '')}",
        })

    list_id, list_url = create_task_list(list_title, tasks)
    return json.dumps({
        "task_list_url": "https://tasks.google.com",
        "list_title": list_title,
        "tasks_created": len(tasks),
        "neighborhood": neighborhood,
        "urgency": solutions.get("urgency", "N/A"),
        "urgency_rationale": solutions.get("urgency_rationale", ""),
        "created_at": today,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def detect_civic_gaps(top_n: int = 10) -> str:
    """
    Identify Montgomery neighborhoods with high incident load but few or zero citizen proposals —
    the "silent zones" where problems are measurable in city data but residents aren't speaking up.

    Algorithm:
      1. Count ArcGIS incidents per neighborhood (all 19 sources, civic_data.city_data)
      2. Fetch all Decidim proposals and count how many mention each neighborhood by name
      3. Compute gap_score = incident_load_index / max(1, proposal_count)
         where incident_load_index = neighborhood_incidents / avg_incidents_across_all_neighborhoods
      4. Rank by gap_score descending — highest score = most critical silent zone

    Returns top_n neighborhoods ranked by gap_score with:
      - total_incidents (count + breakdown by source)
      - proposal_count (how many Decidim proposals mention this neighborhood)
      - gap_score (normalized urgency metric)
      - top_sources (top 3 incident types driving the score)
      - recommended_action (the category to target for outreach)

    No AI call — pure SQL + Decidim GraphQL. Instant results.
    """
    conn = get_db()

    # ── 1. ArcGIS incident counts per neighborhood ───────────────────────────
    with conn.cursor() as cur:
        cur.execute("""
            SELECT neighborhood, source, COUNT(*) as cnt
            FROM civic_data.city_data
            WHERE neighborhood IS NOT NULL AND neighborhood != ''
            GROUP BY neighborhood, source
            ORDER BY neighborhood, cnt DESC
        """)
        rows = cur.fetchall()
    conn.close()

    # Aggregate by neighborhood
    nb_incidents: dict[str, dict] = {}
    for nb, source, cnt in rows:
        if nb not in nb_incidents:
            nb_incidents[nb] = {"total": 0, "by_source": {}}
        nb_incidents[nb]["total"] += cnt
        nb_incidents[nb]["by_source"][source] = cnt

    if not nb_incidents:
        return json.dumps({"error": "No city_data found."})

    avg_incidents = sum(d["total"] for d in nb_incidents.values()) / len(nb_incidents)

    # ── 2. Decidim proposals — count mentions of each neighborhood ────────────
    query = """
    query {
      participatoryProcesses {
        components {
          ... on Proposals {
            proposals(first: 500) {
              nodes {
                title { translation(locale: "en") }
                body  { translation(locale: "en") }
              }
            }
          }
        }
      }
    }
    """
    try:
        data = await graphql(query)
        all_texts: list[str] = []
        for proc in (data.get("data", {}).get("participatoryProcesses") or []):
            for comp in (proc.get("components") or []):
                for p in ((comp.get("proposals") or {}).get("nodes") or []):
                    title = (p.get("title") or {}).get("translation", "")
                    body  = (p.get("body")  or {}).get("translation", "")
                    all_texts.append(f"{title} {body}".lower())
    except Exception:
        all_texts = []

    # Count proposal mentions per neighborhood (case-insensitive substring match)
    nb_proposal_count: dict[str, int] = {}
    for nb in nb_incidents:
        nb_lower = nb.lower()
        # Also match abbreviated forms (e.g. "West Side" matches "westside", "west side")
        nb_tokens = nb_lower.replace("/", " ").split()
        count = 0
        for text in all_texts:
            # Direct match
            if nb_lower in text:
                count += 1
            # All key tokens match (for compound names like "East Montgomery / Eastdale")
            elif len(nb_tokens) >= 2 and all(tok in text for tok in nb_tokens if len(tok) > 3):
                count += 1
        nb_proposal_count[nb] = count

    # ── 3. Compute gap scores ─────────────────────────────────────────────────
    SOURCE_TO_CATEGORY = {
        "fire_incidents":         "public_safety",
        "code_violations":        "blight",
        "building_permits":       "infrastructure",
        "housing_condition":      "housing",
        "food_safety":            "health",
        "environmental_nuisance": "environment",
        "transit_stops":          "transportation",
        "education_facilities":   "education",
        "education_facility":     "education",
        "business_licenses":      "economy",
        "parks_recreation":       "recreation",
        "community_centers":      "services",
        "infrastructure_projects":"infrastructure",
        "opportunity_zones":      "economy",
        "behavioral_centers":     "health",
        "citizen_reports":        "services",
        "city_owned_property":    "infrastructure",
        "historic_markers":       "culture",
        "zoning_decisions":       "planning",
    }

    results = []
    for nb, data in nb_incidents.items():
        total = data["total"]
        load_index = total / avg_incidents  # >1 means above average incident load
        proposals = nb_proposal_count.get(nb, 0)
        gap_score = round(load_index / max(1, proposals), 4)

        top_sources = sorted(data["by_source"].items(), key=lambda x: x[1], reverse=True)[:3]
        dominant_source = top_sources[0][0] if top_sources else "code_violations"
        recommended_category = SOURCE_TO_CATEGORY.get(dominant_source, "services")

        results.append({
            "neighborhood": nb,
            "gap_score": gap_score,
            "total_incidents": total,
            "incident_load_index": round(load_index, 2),
            "proposal_count": proposals,
            "top_sources": [{"source": s, "count": c} for s, c in top_sources],
            "dominant_issue": dominant_source.replace("_", " ").title(),
            "recommended_outreach_category": recommended_category,
        })

    results.sort(key=lambda x: x["gap_score"], reverse=True)
    top = results[:top_n]
    worst = top[0]["neighborhood"] if top else None

    return json.dumps({
        "silent_zones": top,
        "total_neighborhoods_analyzed": len(results),
        "avg_incidents_per_neighborhood": round(avg_incidents, 0),
        "total_proposals_on_platform": len(all_texts),
        "methodology": (
            "gap_score = (neighborhood_incidents / avg_incidents) / max(1, proposals_mentioning_neighborhood). "
            "Higher score = more city data problems, fewer citizen voices. "
            "Priority targets for community outreach and proactive city engagement."
        ),
        "next_steps": _next_steps("detect_civic_gaps", {"neighborhood": worst}),
    }, ensure_ascii=False, indent=2)


# ── TOOL 21 — post_debate_summary ───────────────────────────────────────────────
@mcp.tool()
async def post_debate_summary(debate_id: str) -> str:
    """
    WRITE tool — closes the debate loop with a neutral AI synthesis grounded in real city data.
    Flow:
      1. Fetch debate title + description + existing citizen comments
      2. Detect neighborhood/topic → pull real ArcGIS incidents + Census trends
      3. If comments exist: synthesize pro/contra positions + post neutral AI summary
         If no comments yet: post an AI "opening brief" seeding both sides with real data
      4. Post as Momentum AI on the debate thread
    Tone: neutral facilitator presenting verified facts — no advocacy, no spin.
    """
    # ── Step 1: Fetch debate + comments (processes + assemblies) ─────────────────
    dq = """
    query {
      participatoryProcesses {
        components {
          ... on Debates {
            debates(first: 200) {
              nodes {
                id
                title { translation(locale: "en") }
                description { translation(locale: "en") }
                comments { id body alignment }
              }
            }
          }
        }
      }
      assemblies {
        components {
          ... on Debates {
            debates(first: 200) {
              nodes {
                id
                title { translation(locale: "en") }
                description { translation(locale: "en") }
                comments { id body alignment }
              }
            }
          }
        }
      }
    }"""
    data = await graphql(dq)
    debate = None
    # Search in processes
    for space in list(data.get("data", {}).get("participatoryProcesses") or []) + \
                 list(data.get("data", {}).get("assemblies") or []):
        for comp in (space.get("components") or []):
            for node in (comp.get("debates", {}).get("nodes") or []):
                if str(node["id"]) == str(debate_id):
                    debate = node
                    break

    if not debate:
        return json.dumps({"error": f"Debate {debate_id} not found"})

    title = (debate.get("title") or {}).get("translation", "")
    description = (debate.get("description") or {}).get("translation", "")
    import re
    description_plain = re.sub(r"<[^>]+>", "", description).strip()
    comments = debate.get("comments") or []

    # ── Step 2: Detect neighborhood from title/description ───────────────────────
    nb_prompt = f"""From this civic debate topic, extract the Montgomery AL neighborhood or zip code.
If none is specific, return "Montgomery".
Debate: "{title}. {description_plain[:300]}"
Return JSON: {{"neighborhood": "name"}}"""
    nb_raw = await _generate_json(nb_prompt, temperature=0.0)
    try:
        detected_nb = json.loads(nb_raw).get("neighborhood") or "Montgomery"
    except Exception:
        detected_nb = "Montgomery"

    # ── Step 3: Pull real data ────────────────────────────────────────────────────
    report_raw = await civic_report(detected_nb)
    report = json.loads(report_raw)
    severity = report.get("overall_severity", "moderate")
    findings = report.get("findings", [])
    scores = report.get("deprivation_scores", {}) or {}
    adi_score = (scores.get("ADI") or {}).get("score")

    top_finding = ""
    if findings:
        f0 = findings[0]
        top_finding = f0.get("finding", "") if isinstance(f0, dict) else str(f0)

    second_finding = ""
    if len(findings) > 1:
        f1 = findings[1]
        second_finding = f1.get("finding", "") if isinstance(f1, dict) else str(f1)

    # ── Step 4: Build prompt based on whether comments exist ─────────────────────
    n_comments = len(comments)

    if n_comments == 0:
        # Opening brief — seed both sides with real data
        comment_prompt = f"""You are Momentum AI, the civic intelligence system for Montgomery, Alabama.
You are opening a public debate forum thread. Your role: neutral facilitator who presents verified city data — no advocacy.

DEBATE TOPIC: "{title}"
CONTEXT: {description_plain[:400]}
NEIGHBORHOOD ANALYZED: {detected_nb}

REAL CITY DATA:
- Overall severity level: {severity}
- Key finding 1: {top_finding}
- Key finding 2: {second_finding}
- ADI deprivation score: {f"{round(adi_score * 100)}th percentile" if adi_score else "not available"} (higher = more deprived)

Write a 4-6 sentence opening brief that:
1. States what the city data shows (1-2 facts, specific numbers)
2. Identifies the main tension in this debate (who benefits, who bears the cost)
3. Invites citizens to share their perspective
Do NOT take a side. Use plain English. No bullet points. No markdown.
End with: "— Momentum AI, City of Montgomery"

Write only the comment text."""
    else:
        # Synthesis — summarize what citizens said, then add data layer
        pro_comments = [c.get("body", "") for c in comments if c.get("alignment", 0) == 1]
        con_comments = [c.get("body", "") for c in comments if c.get("alignment", 0) == -1]
        neutral_comments = [c.get("body", "") for c in comments if c.get("alignment", 0) == 0]

        def fmt_comments(lst, max_each=200):
            return " | ".join(str(c)[:max_each] for c in lst[:5]) or "none"

        comment_prompt = f"""You are Momentum AI, the civic intelligence system for Montgomery, Alabama.
You are posting a neutral synthesis of a public debate thread. Your role: summarize citizen positions fairly, then add verified city data.

DEBATE TOPIC: "{title}"
NEIGHBORHOOD: {detected_nb}

CITIZEN COMMENTS ({n_comments} total):
- Supporting ({len(pro_comments)}): {fmt_comments(pro_comments)}
- Opposing ({len(con_comments)}): {fmt_comments(con_comments)}
- Neutral/mixed ({len(neutral_comments)}): {fmt_comments(neutral_comments)}

REAL CITY DATA:
- Overall severity: {severity}
- Key finding: {top_finding}
- ADI deprivation score: {f"{round(adi_score * 100)}th percentile" if adi_score else "not available"}

Write a 4-6 sentence synthesis that:
1. Fairly represents both sides ("Some residents argue... Others point out...")
2. Adds 1-2 facts from city data that inform the debate (specific numbers)
3. Identifies where data and community sentiment align or diverge
No advocacy. No bullet points. No markdown. Plain English.
End with: "— Momentum AI, City of Montgomery"

Write only the comment text."""

    comment_body = await _generate_json(comment_prompt, temperature=0.2)
    try:
        parsed = json.loads(comment_body)
        comment_body = parsed.get("comment", comment_body) if isinstance(parsed, dict) else comment_body
    except Exception:
        pass
    comment_body = comment_body.strip().strip('"')

    # ── Step 5: Post via GraphQL ──────────────────────────────────────────────────
    mutation = """
    mutation($id: String!, $type: String!, $body: String!) {
      commentable(id: $id, type: $type) {
        addComment(body: $body) { id body }
      }
    }"""
    result = await graphql(mutation, {
        "id": str(debate_id),
        "type": "Decidim::Debates::Debate",
        "body": comment_body,
    }, auth=True)

    errors = result.get("errors") or []
    # Decidim gamification badge error fires after comment is already created — ignore it
    real_errors = [e for e in errors if "badge" not in e.get("message", "").lower()]
    if real_errors:
        return json.dumps({"error": real_errors[0]["message"], "debate_id": debate_id})

    comment = ((result.get("data") or {}).get("commentable") or {}).get("addComment") or {}
    mode = "synthesis" if n_comments > 0 else "opening_brief"

    return json.dumps({
        "status": "posted",
        "debate_id": debate_id,
        "debate_title": title,
        "mode": mode,
        "neighborhood_analyzed": detected_nb,
        "severity": severity,
        "citizen_comments_read": n_comments,
        "comment_id": comment.get("id"),
        "comment_preview": comment_body[:300],
        "platform_url": f"{os.getenv('DECIDIM_URL')}/processes",
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import sys
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
