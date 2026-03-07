"""
Momentum MGM — Embedding Backfill
Reads existing civic_data records (properties, businesses) and generates
pgvector embeddings via gemini-embedding-001 (3072d).
Run once after initial data lake collection.
"""
import os
import uuid
import time
import logging
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
from google import genai as google_genai

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [embed] %(message)s")
log = logging.getLogger("embed")

DB = {"host": "127.0.0.1", "port": 5432, "dbname": "momentum", "user": "nodebb", "password": "superSecret123"}
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
_gemini = google_genai.Client(api_key=GOOGLE_API_KEY)


def embed(text: str) -> list | None:
    try:
        r = _gemini.models.embed_content(model="models/gemini-embedding-001", contents=text[:2000])
        return r.embeddings[0].values
    except Exception as e:
        log.warning(f"Embed failed: {e}")
        return None


def store(conn, source_table, source_id, neighborhood, category, content, vec):
    vec_str = "[" + ",".join(str(v) for v in vec) + "]"
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO civic_data.embeddings
               (id, source_table, source_id, neighborhood, civic_category, content_text, embedding)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING""",
            (str(uuid.uuid4()), source_table, source_id, neighborhood, category, content[:1000], vec_str),
        )
    conn.commit()


def backfill_properties(conn):
    log.info("Backfilling properties (Zillow)...")
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT p.id, p.address, p.neighborhood, p.price, p.bedrooms, p.bathrooms,
                   p.property_type, p.days_on_market
            FROM civic_data.properties p
            WHERE p.id NOT IN (
                SELECT source_id FROM civic_data.embeddings WHERE source_table = 'properties'
            )
        """)
        rows = cur.fetchall()
    log.info(f"  {len(rows)} properties to embed")
    for i, r in enumerate(rows):
        content = (
            f"{r['address'] or ''} in {r['neighborhood'] or 'Montgomery'} — "
            f"{r['property_type'] or 'property'}, "
            f"{r['bedrooms'] or '?'}bd/{r['bathrooms'] or '?'}ba, "
            f"${r['price'] or '?'}, {r['days_on_market'] or '?'} days on market"
        )
        vec = embed(content)
        if vec:
            store(conn, "properties", str(r["id"]), r["neighborhood"], "housing", content, vec)
        if (i + 1) % 50 == 0:
            log.info(f"  {i+1}/{len(rows)} done")
    log.info(f"  Properties done: {len(rows)} embedded")


def backfill_businesses(conn):
    log.info("Backfilling businesses (Yelp)...")
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT b.id, b.name, b.category, b.neighborhood, b.rating,
                   b.review_count, b.is_closed
            FROM civic_data.businesses b
            WHERE NOT EXISTS (
                SELECT 1 FROM civic_data.embeddings e
                WHERE e.source_table = 'businesses' AND e.source_id = b.id
            )
        """)
        rows = cur.fetchall()
    log.info(f"  {len(rows)} businesses to embed")
    for i, r in enumerate(rows):
        content = (
            f"{r['name'] or ''} ({r['category'] or 'business'}) in {r['neighborhood'] or 'Montgomery'} — "
            f"rating {r['rating'] or '?'}/5, {r['review_count'] or 0} reviews, "
            f"{'closed' if r['is_closed'] else 'open'}"
        )
        vec = embed(content)
        if vec:
            store(conn, "businesses", str(r["id"]), r["neighborhood"], "economy", content, vec)
        if (i + 1) % 50 == 0:
            log.info(f"  {i+1}/{len(rows)} done")
    log.info(f"  Businesses done: {len(rows)} embedded")


SOURCE_CATEGORY_MAP = {
    "fire_incidents":        "public_safety",
    "code_violations":       "housing",
    "building_permits":      "housing",
    "housing_condition":     "housing",
    "transit_stops":         "transportation",
    "food_safety":           "health",
    "environmental_nuisance":"environment",
    "education_facilities":  "education",
    "citizen_reports":       "governance",
    "behavioral_centers":    "health",
    "opportunity_zones":     "economy",
    "infrastructure_projects":"infrastructure",
    "parks_recreation":      "parks_culture",
    "city_owned_property":   "governance",
    "zoning_decisions":      "governance",
    "business_licenses":     "economy",
    "historic_markers":      "parks_culture",
    "community_centers":     "parks_culture",
    "education_facility":    "education",
}


def backfill_city_data(conn, batch_size: int = 100):
    log.info("Backfilling city_data (ArcGIS — 44K records)...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM civic_data.city_data cd
            WHERE NOT EXISTS (
                SELECT 1 FROM civic_data.embeddings e
                WHERE e.source_table = 'city_data' AND e.source_id = cd.id
            )
        """)
        total_pending = cur.fetchone()[0]
    log.info(f"  {total_pending} city_data records to embed")

    embedded = 0
    offset = 0
    while True:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT cd.id, cd.source, cd.category, cd.neighborhood,
                       cd.address, cd.status, cd.reported_at
                FROM civic_data.city_data cd
                WHERE NOT EXISTS (
                    SELECT 1 FROM civic_data.embeddings e
                    WHERE e.source_table = 'city_data' AND e.source_id = cd.id
                )
                ORDER BY cd.reported_at DESC NULLS LAST
                LIMIT %s
            """, (batch_size,))
            rows = cur.fetchall()

        if not rows:
            break

        for r in rows:
            source = r["source"] or "unknown"
            neighborhood = r["neighborhood"] or "Montgomery"
            address = r["address"] or ""
            status = r["status"] or ""
            reported = str(r["reported_at"])[:10] if r["reported_at"] else ""
            category = SOURCE_CATEGORY_MAP.get(source, "governance")

            content = f"{source.replace('_', ' ').title()} at {address} in {neighborhood}"
            if status:
                content += f" — {status}"
            if reported:
                content += f" ({reported})"

            vec = embed(content)
            if vec:
                store(conn, "city_data", str(r["id"]), neighborhood, category, content, vec)
                embedded += 1

        offset += len(rows)
        log.info(f"  {offset}/{total_pending} processed, {embedded} embedded so far")
        time.sleep(0.05)  # ~20 req/s — stay under Gemini embedding rate limit

    log.info(f"  city_data done: {embedded} embedded")


def main():
    if not GOOGLE_API_KEY:
        log.error("GOOGLE_API_KEY not set")
        return
    conn = psycopg2.connect(**DB)
    backfill_properties(conn)
    backfill_businesses(conn)
    backfill_city_data(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM civic_data.embeddings")
        total = cur.fetchone()[0]
    conn.close()
    log.info(f"Backfill complete — {total} total embeddings in DB")


if __name__ == "__main__":
    main()
