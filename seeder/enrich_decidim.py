"""
enrich_decidim.py — LE COEUR de Momentum MGM
Quand un citoyen poste une proposal -> Grok lit le data lake -> répond dans Decidim.

Usage:
  python enrich_decidim.py          # enrichit toutes les proposals non traitées
  python enrich_decidim.py --id 52  # enrichit une proposal spécifique
  python enrich_decidim.py --dry-run # montre ce qui serait posté sans poster
"""

import os
import sys
import json
import argparse
import httpx
import psycopg2
import psycopg2.extras
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────

DECIDIM_URL = os.getenv("DECIDIM_URL", "http://localhost:3000")
DECIDIM_HOST = "mgm.styxcore.dev"
DECIDIM_API_KEY = os.getenv("DECIDIM_API_KEY")
DECIDIM_API_SECRET = os.getenv("DECIDIM_API_SECRET")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

DB = {
    "host": "127.0.0.1", "port": 5432,
    "dbname": "momentum", "user": "nodebb", "password": "superSecret123",
}

AI_MODEL = "x-ai/grok-4"
AI_DISCLAIMER = "**[Momentum AI — Open Data Montgomery]**\n"

# Known neighborhood names to detect in proposal text
KNOWN_NEIGHBORHOODS = [
    "West Side", "Westside", "North Montgomery", "Chisholm", "Midtown",
    "Cloverdale", "Downtown", "West End", "East Montgomery", "South Montgomery",
    "EastChase", "Dalraida", "Vaughn", "South Side", "Capitol Heights",
    "Old Cloverdale", "Southlawn", "Perkins", "Garden District", "Peacock Tract",
    "Coliseum", "Forest Avenue", "Mobile Heights", "Trenholm Court",
]


# ── Decidim API client ─────────────────────────────────────────────────────────

class DecidimAPI:
    """HTTP client for Decidim GraphQL API — read (no auth) + write (JWT)."""

    def __init__(self):
        self._jwt = None
        self._client = httpx.Client(timeout=30, follow_redirects=True)

    def _headers(self, auth=False):
        h = {"Content-Type": "application/json", "Host": DECIDIM_HOST}
        if auth and self._jwt:
            h["Authorization"] = f"Bearer {self._jwt}"
        return h

    def authenticate(self):
        r = self._client.post(
            f"{DECIDIM_URL}/api/sign_in",
            json={"api_user": {"key": DECIDIM_API_KEY, "secret": DECIDIM_API_SECRET}},
            headers={"Content-Type": "application/json", "Host": DECIDIM_HOST},
        )
        data = r.json()
        self._jwt = data.get("jwt_token")
        if not self._jwt:
            print(f"[AUTH ERROR] {data}")
            return False
        print(f"[AUTH] Authenticated as {data.get('name')} (id={data.get('id')})")
        return True

    def mutate(self, gql, variables=None):
        r = self._client.post(
            f"{DECIDIM_URL}/api",
            json={"query": gql, "variables": variables or {}},
            headers=self._headers(auth=True),
        )
        return r.json()

    def add_comment(self, proposal_id, body):
        result = self.mutate(
            """
            mutation AddComment($id: String!, $body: String!) {
              commentable(id: $id, type: "Decidim::Proposals::Proposal") {
                addComment(body: $body) {
                  id
                }
              }
            }
            """,
            {"id": str(proposal_id), "body": body},
        )
        errors = result.get("errors")
        if errors:
            print(f"[MUTATION ERROR] {errors}")
            return None
        return result.get("data", {}).get("commentable", {}).get("addComment", {}).get("id")

    def close(self):
        self._client.close()


# ── Data lake ──────────────────────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(**DB)


def get_proposals_to_enrich(specific_id=None):
    conn = get_db()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if specific_id:
            cur.execute("""
                SELECT id,
                       title->>'en' AS title_en,
                       body->>'en'  AS body_en,
                       decidim_component_id AS component_id
                FROM decidim_proposals_proposals
                WHERE id = %s
            """, (specific_id,))
        else:
            cur.execute("""
                SELECT p.id,
                       p.title->>'en' AS title_en,
                       p.body->>'en'  AS body_en,
                       p.decidim_component_id AS component_id
                FROM decidim_proposals_proposals p
                WHERE p.title->>'en' IS NOT NULL
                  AND p.title->>'en' != ''
                  AND NOT EXISTS (
                    SELECT 1 FROM civic_data.reports r
                    WHERE r.report_type = 'proposal_enrichment'
                      AND r.subject = p.id::text
                  )
                ORDER BY p.id
            """)
        rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def detect_neighborhood(title, body):
    text = (title or "") + " " + (body or "")
    for nb in KNOWN_NEIGHBORHOODS:
        if nb.lower() in text.lower():
            return nb
    return None


def _query_city_sources(cur, nb):
    """Query city_data + businesses for a given neighborhood (None = city-wide)."""
    sources = {}
    nb_arg = (nb, f"%{nb}%" if nb else None)

    cur.execute("""
        SELECT COUNT(*) as cnt FROM civic_data.city_data
        WHERE source = 'code_violations' AND (%s IS NULL OR neighborhood ILIKE %s)
    """, nb_arg)
    n = cur.fetchone()["cnt"]
    if n:
        sources["code_violations"] = {"total": n}

    cur.execute("""
        SELECT COUNT(*) as cnt FROM civic_data.city_data
        WHERE source = 'building_permits' AND (%s IS NULL OR neighborhood ILIKE %s)
    """, nb_arg)
    n = cur.fetchone()["cnt"]
    if n:
        sources["building_permits"] = {"total": n}

    cur.execute("""
        SELECT COUNT(*) as cnt FROM civic_data.city_data
        WHERE source = 'fire_incidents' AND (%s IS NULL OR neighborhood ILIKE %s)
    """, nb_arg)
    n = cur.fetchone()["cnt"]
    if n:
        sources["fire_incidents"] = {"total": n}

    cur.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN is_closed THEN 1 ELSE 0 END) as closed,
               ROUND(AVG(rating)::numeric, 2) as avg_rating
        FROM civic_data.businesses
        WHERE (%s IS NULL OR neighborhood ILIKE %s)
    """, nb_arg)
    biz = cur.fetchone()
    if biz and biz["total"]:
        sources["businesses"] = {
            "total": biz["total"],
            "closed": biz["closed"],
            "avg_rating": float(biz["avg_rating"]) if biz["avg_rating"] else None,
        }

    return sources


def get_data_lake_context(neighborhood):
    conn = get_db()
    nb = neighborhood
    ctx = {"neighborhood": nb or "Montgomery (city-wide)", "sources": {}}

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Census: neighborhood-specific (71 tracts have real data)
        cur.execute("""
            SELECT metric, ROUND(AVG(value)::numeric, 1) as avg_val
            FROM civic_data.census
            WHERE metric IN ('median_income','poverty_below','housing_vacant','unemployed','median_rent')
              AND (%s IS NULL OR neighborhood ILIKE %s)
              AND year >= 2020 AND value > 0
            GROUP BY metric
        """, (nb, f"%{nb}%" if nb else None))
        rows = cur.fetchall()
        if rows:
            ctx["sources"]["census"] = {r["metric"]: float(r["avg_val"]) for r in rows}

        # City data: neighborhood-specific first, fall back to city-wide if no results
        city_sources = _query_city_sources(cur, nb)
        if not city_sources and nb:
            print(f"  no city_data for '{nb}' — falling back to city-wide")
            ctx["neighborhood"] = "Montgomery (city-wide)"
            city_sources = _query_city_sources(cur, None)
        ctx["sources"].update(city_sources)

    conn.close()
    return ctx


def save_report(proposal_id, neighborhood, payload):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO civic_data.reports (report_type, subject, generated_by, payload)
            VALUES ('proposal_enrichment', %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (str(proposal_id), AI_MODEL, json.dumps(payload)))
    conn.commit()
    conn.close()


# ── AI ─────────────────────────────────────────────────────────────────────────

def build_prompt(proposal, ctx):
    """Data brief — conditions, not people. Numbers speak. No interpretation.
    Returns (prompt_str, data_lines) or (None, []) if nothing relevant.
    Hard filter: no race/ethnicity/demographic breakdowns — civic conditions only.
    """
    nb = ctx["neighborhood"]
    sources = ctx["sources"]
    data_lines = []

    if "code_violations" in sources:
        data_lines.append(f"code_violations ({nb}): {sources['code_violations']['total']}")
    if "building_permits" in sources:
        data_lines.append(f"building_permits ({nb}): {sources['building_permits']['total']}")
    if "fire_incidents" in sources:
        data_lines.append(f"fire_incidents ({nb}): {sources['fire_incidents']['total']}")
    if "businesses" in sources:
        b = sources["businesses"]
        s = f"businesses ({nb}): {b['total']} total"
        if b["closed"]:
            s += f", {b['closed']} permanently closed"
        if b["avg_rating"]:
            s += f", avg rating {b['avg_rating']}"
        data_lines.append(s)
    if "census" in sources:
        c = sources["census"]
        # Aggregate civic conditions only — no demographic/racial breakdowns
        for k, fmt in [
            ("median_income",  "median_household_income ({nb}): ${v:,.0f}"),
            ("median_rent",    "median_rent ({nb}): ${v:,.0f}/month"),
            ("housing_vacant", "vacant_housing_units ({nb}): {v:,.0f}"),
            ("unemployed",     "unemployed_residents ({nb}): {v:,.0f}"),
            ("poverty_below",  "residents_below_poverty_line ({nb}): {v:,.0f}"),
        ]:
            if k in c:
                data_lines.append(fmt.format(nb=nb, v=c[k]))

    if not data_lines:
        return None, []

    data_block = "\n".join(f"- {l}" for l in data_lines)

    prompt = f"""Civic data system for Montgomery AL. A citizen submitted a proposal. Select only the data points factually relevant to this specific civic issue and output them as a markdown bullet list.

RULES:
- Bullets only. No greeting, no conclusion, no interpretation, no advice.
- Pick only metrics relevant to the issue (infrastructure → violations/permits, safety → fire incidents, housing → vacancy/rent, economy → businesses/income).
- Irrelevant metrics: omit entirely.
- No relevant metrics at all: output exactly SKIP
- Max 4 bullets. One fact per bullet.

CIVIC ISSUE: {proposal['title_en']}
{proposal['body_en'] or ''}

AVAILABLE DATA:
{data_block}

Output:"""

    return prompt, data_lines


def call_grok(prompt):
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
    r = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
    )
    return r.choices[0].message.content.strip()


# ── Main ───────────────────────────────────────────────────────────────────────

def enrich_proposal(api, proposal, dry_run=False):
    pid = proposal["id"]
    title = proposal["title_en"] or ""
    body = proposal["body_en"] or ""

    print(f"\n[PROPOSAL {pid}] {title[:70]}")

    neighborhood = detect_neighborhood(title, body)
    print(f"  neighborhood: {neighborhood or 'city-wide'}")

    ctx = get_data_lake_context(neighborhood)
    print(f"  data sources: {list(ctx['sources'].keys())}")

    prompt, data_lines = build_prompt(proposal, ctx)
    if not prompt:
        print("  no relevant data — skipping")
        return True  # not an error, just nothing to say

    print(f"  calling {AI_MODEL} ({len(data_lines)} data points)...")
    ai_text = call_grok(prompt)

    if not ai_text or ai_text.strip().upper() == "SKIP":
        print("  no relevant data per AI — skipping")
        return True

    comment = AI_DISCLAIMER + ai_text
    print(f"  response ({len(ai_text)} chars)")

    if dry_run:
        print(f"  [DRY RUN] skipping post")
        print(f"\n--- FULL RESPONSE ---\n{comment}\n---")
        return True

    comment_id = api.add_comment(pid, comment)
    if not comment_id:
        print("  ERROR: comment post failed")
        return False

    print(f"  comment posted (id={comment_id})")

    save_report(pid, neighborhood, {
        "proposal_id": pid,
        "title": title,
        "neighborhood": neighborhood,
        "comment_id": comment_id,
        "data_sources": list(ctx["sources"].keys()),
    })
    print("  report saved")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if not DECIDIM_API_KEY or not DECIDIM_API_SECRET:
        print("ERROR: DECIDIM_API_KEY / DECIDIM_API_SECRET missing from .env")
        sys.exit(1)
    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY missing from .env")
        sys.exit(1)

    api = DecidimAPI()
    if not args.dry_run:
        if not api.authenticate():
            sys.exit(1)

    proposals = get_proposals_to_enrich(specific_id=args.id)
    if not proposals:
        print("No proposals to enrich — all up to date.")
        api.close()
        return

    if args.limit:
        proposals = proposals[:args.limit]

    print(f"\nEnriching {len(proposals)} proposal(s)...")

    ok = 0
    for p in proposals:
        if enrich_proposal(api, p, dry_run=args.dry_run):
            ok += 1

    api.close()
    print(f"\nDone: {ok}/{len(proposals)} enriched")


if __name__ == "__main__":
    main()
