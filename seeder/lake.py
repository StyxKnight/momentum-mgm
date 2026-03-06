"""
Momentum MGM — Civic Data Lake
Initial collection from Bright Data datasets + Census ACS API.
Populates civic_data schema in PostgreSQL with real Montgomery, AL data.

Usage:
  python lake.py --source all
  python lake.py --source zillow
  python lake.py --source yelp
  python lake.py --source google_maps
  python lake.py --source indeed
  python lake.py --source census
  python lake.py --source all --embed   # also generate pgvector embeddings
"""

import os
import sys
import json
import time
import asyncio
import argparse
import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv
from brightdata import BrightDataClient
from google import genai as google_genai

load_dotenv(Path(__file__).parent.parent / ".env")

# ── Config ────────────────────────────────────────────────────────────────────

BRIGHT_DATA_TOKEN = os.getenv("BRIGHT_DATA_API_KEY")
GOOGLE_API_KEY    = os.getenv("GOOGLE_API_KEY")

DB = {
    "host":     "127.0.0.1",
    "port":     5432,
    "dbname":   "momentum",
    "user":     "nodebb",
    "password": "superSecret123",
}

MONTGOMERY_FILTER = {
    "operator": "and",
    "filters": [
        {"name": "city",  "operator": "=", "value": "Montgomery"},
        {"name": "state", "operator": "=", "value": "AL"},
    ],
}

# Census ACS 5-year estimates — Montgomery County AL
# FIPS: state=01 (Alabama), county=101 (Montgomery County)
CENSUS_STATE   = "01"
CENSUS_COUNTY  = "101"
CENSUS_YEARS   = list(range(2010, 2025))  # 2010–2024

CENSUS_VARS = {
    "median_income":      "B19013_001E",
    "poverty_total":      "B17001_001E",
    "poverty_below":      "B17001_002E",
    "population":         "B01001_001E",
    "housing_total":      "B25002_001E",
    "housing_vacant":     "B25002_003E",
    "labor_force":        "B23025_002E",
    "unemployed":         "B23025_005E",
    "median_rent":        "B25064_001E",
    "owner_occupied":     "B25003_002E",
    "renter_occupied":    "B25003_003E",
    "edu_total":          "B15003_001E",
    "edu_bachelors_plus": "B15003_022E",
}

RECORDS_LIMIT = 500

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lake")

# ── Database ──────────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(**DB)


def log_run_start(conn, source: str) -> str:
    run_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO civic_data.siphon_runs (id, source, status, started_at)
               VALUES (%s, %s, 'running', NOW())""",
            (run_id, source),
        )
    conn.commit()
    return run_id


def log_run_end(conn, run_id: str, collected: int, upserted: int, embedded: int, error: str = None):
    status = "error" if error else "success"
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE civic_data.siphon_runs
               SET status=%s, records_collected=%s, records_upserted=%s,
                   records_embedded=%s, error_message=%s, completed_at=NOW()
               WHERE id=%s""",
            (status, collected, upserted, embedded, error, run_id),
        )
    conn.commit()


# ── Geocoding — Nominatim ────────────────────────────────────────────────────

_geo_cache = {}

def reverse_geocode(lat: float, lon: float) -> str:
    """lat/lon → neighborhood name via Nominatim. Rate-limited 1 req/sec. Cached."""
    if lat is None or lon is None:
        return "Montgomery"
    key = (round(lat, 3), round(lon, 3))
    if key in _geo_cache:
        return _geo_cache[key]

    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 14},
            headers={"User-Agent": "MomentumMGM/1.0 civic-ai-platform"},
            timeout=10,
        )
        addr = r.json().get("address", {})
        name = (
            addr.get("suburb")
            or addr.get("neighbourhood")
            or addr.get("city_district")
            or addr.get("town")
            or "Montgomery"
        )
        time.sleep(1.1)  # Nominatim rate limit: 1 req/sec
    except Exception as e:
        log.warning(f"Geocoding failed ({lat},{lon}): {e}")
        name = "Montgomery"

    _geo_cache[key] = name
    return name


def upsert_neighborhood(conn, name: str, tract: str = None):
    """Register a neighborhood name in the reference table."""
    if not name or name == "Montgomery":
        return
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO civic_data.neighborhoods (census_tract, name)
               VALUES (%s, %s)
               ON CONFLICT (census_tract) DO NOTHING""",
            (tract or name, name),
        )
    conn.commit()


# ── Embeddings — Google Gemini gemini-embedding-001 (3072d, Matryoshka) ─────────────────────

_gemini = google_genai.Client(api_key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None


def embed_text(text: str) -> Optional[list]:
    """Embed text using Google Gemini gemini-embedding-001 (3072 dimensions, Matryoshka)."""
    if not _gemini or not text:
        return None
    try:
        result = _gemini.models.embed_content(
            model="models/gemini-embedding-001",
            contents=text,
        )
        return result.embeddings[0].values
    except Exception as e:
        log.warning(f"Embedding failed: {e}")
        return None


def store_embedding(conn, source_table: str, source_id: str, neighborhood: str,
                    civic_category: str, content_text: str, embedding: list):
    if not embedding:
        return
    vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO civic_data.embeddings
               (id, source_table, source_id, neighborhood, civic_category, content_text, embedding)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING""",
            (str(uuid.uuid4()), source_table, source_id, neighborhood,
             civic_category, content_text[:1000], vec_str),
        )
    conn.commit()


# ── Bright Data download (bypass SDK race condition bug — see BUG-022) ────────

def brightdata_download(snapshot_id: str) -> list:
    """
    Download a Bright Data snapshot via direct REST API.
    Handles two snapshot types:
    - snap_* : SDK-triggered → status via /snapshots/{id}, download via /snapshots/{id}/download
    - sd_*   : v3/trigger-triggered → status via /v3/progress/{id}, download via /v3/download/{id}
    """
    headers = {"Authorization": f"Bearer {BRIGHT_DATA_TOKEN}"}
    is_v3 = snapshot_id.startswith("sd_")

    for attempt in range(40):  # poll up to 40 × 30s = 20 min
        # Check status
        if is_v3:
            status_r = requests.get(
                f"https://api.brightdata.com/datasets/v3/progress/{snapshot_id}",
                headers=headers, timeout=30
            )
            status = status_r.json().get("status", "")
            if status == "failed":
                raise RuntimeError(f"Snapshot {snapshot_id} failed: {status_r.json()}")
            if status != "ready":
                log.info(f"  Snapshot {snapshot_id}: {status} (attempt {attempt+1}/40), waiting 30s...")
                time.sleep(30)
                continue
            download_url = f"https://api.brightdata.com/datasets/v3/download/{snapshot_id}"
        else:
            download_url = f"https://api.brightdata.com/datasets/snapshots/{snapshot_id}/download"

        # Download
        r = requests.get(download_url, params={"format": "jsonl"}, headers=headers, timeout=60)
        if r.status_code == 200 and r.text.strip() and "Snapshot is building" not in r.text:
            lines = [l for l in r.text.strip().split("\n") if l.strip()]
            return [json.loads(l) for l in lines]
        log.info(f"  Snapshot {snapshot_id}: not ready yet (attempt {attempt+1}/40), waiting 30s...")
        time.sleep(30)

    raise TimeoutError(f"Snapshot {snapshot_id} not downloadable after 20 min")


# ── Source: Zillow ────────────────────────────────────────────────────────────

async def collect_zillow(conn, run_id: str, do_embed: bool) -> tuple[int, int, int]:
    log.info("Collecting Zillow properties for Montgomery, AL...")
    collected = upserted = embedded = 0

    async with BrightDataClient(token=BRIGHT_DATA_TOKEN) as client:
        snapshot_id = await client.datasets.zillow_properties(
            filter=MONTGOMERY_FILTER,
            records_limit=RECORDS_LIMIT,
        )
        log.info(f"  Zillow snapshot: {snapshot_id} — waiting for data...")
    records = brightdata_download(snapshot_id)

    log.info(f"  Got {len(records)} Zillow records")
    collected = len(records)

    for r in records:
        lat = r.get("latitude") or r.get("lat")
        lon = r.get("longitude") or r.get("lon") or r.get("lng")
        neighborhood = reverse_geocode(lat, lon) if lat and lon else "Montgomery"
        upsert_neighborhood(conn, neighborhood)

        ext_id = str(r.get("zpid") or r.get("id") or r.get("url") or uuid.uuid4())
        price = r.get("price") or r.get("unformattedPrice")
        sqft  = r.get("area") or r.get("sqft") or r.get("livingArea")

        content = (
            f"{r.get('address', '')} in {neighborhood} — "
            f"{r.get('propertyType', 'property')}, "
            f"{r.get('bedrooms', '?')}bd/{r.get('bathrooms', '?')}ba, "
            f"${price}, {r.get('daysOnMarket', '?')} days on market"
        )

        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO civic_data.properties
                   (id, source, external_id, address, neighborhood,
                    latitude, longitude, price, sqft, bedrooms, bathrooms,
                    property_type, days_on_market, raw_data, collected_at)
                   VALUES (%s,'zillow',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                   ON CONFLICT (source, external_id) DO UPDATE SET
                     price=EXCLUDED.price, days_on_market=EXCLUDED.days_on_market,
                     collected_at=NOW(), raw_data=EXCLUDED.raw_data
                   RETURNING id""",
                (
                    str(uuid.uuid4()), ext_id,
                    r.get("address"), neighborhood, lat, lon,
                    price, sqft,
                    r.get("bedrooms"), r.get("bathrooms"),
                    r.get("propertyType"), r.get("daysOnMarket"),
                    json.dumps(r),
                ),
            )
            row = cur.fetchone()
            conn.commit()
            upserted += 1

            if do_embed and row:
                vec = embed_text(content)
                if vec:
                    store_embedding(conn, "properties", str(row[0]),
                                    neighborhood, "housing", content, vec)
                    embedded += 1

    log.info(f"  Zillow: {upserted} upserted, {embedded} embedded")
    return collected, upserted, embedded


# ── Source: Yelp ─────────────────────────────────────────────────────────────

async def collect_yelp(conn, run_id: str, do_embed: bool) -> tuple[int, int, int]:
    log.info("Collecting Yelp businesses for Montgomery, AL...")
    collected = upserted = embedded = 0

    async with BrightDataClient(token=BRIGHT_DATA_TOKEN) as client:
        snapshot_id = await client.datasets.yelp_businesses(
            filter=MONTGOMERY_FILTER,
            records_limit=RECORDS_LIMIT,
        )
        log.info(f"  Yelp snapshot: {snapshot_id} — waiting...")
        records = brightdata_download(snapshot_id)

    log.info(f"  Got {len(records)} Yelp records")
    collected = len(records)

    for r in records:
        lat = r.get("latitude")
        lon = r.get("longitude")
        neighborhood = reverse_geocode(lat, lon) if lat and lon else "Montgomery"
        upsert_neighborhood(conn, neighborhood)

        ext_id = str(r.get("business_id") or r.get("yelp_biz_id") or r.get("url") or uuid.uuid4())
        category = r.get("categories")
        if isinstance(category, list):
            category = category[0] if category else None

        content = (
            f"{r.get('name', '')} ({category or 'business'}) in {neighborhood} — "
            f"rating {r.get('overall_rating', '?')}/5, "
            f"{r.get('reviews_count', 0)} reviews, "
            f"{'closed' if r.get('is_closed') else 'open'}"
        )

        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO civic_data.businesses
                   (id, source, external_id, name, category, neighborhood,
                    address, latitude, longitude, rating, review_count,
                    price_range, is_closed, raw_data, collected_at)
                   VALUES (%s,'yelp',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                   ON CONFLICT (source, external_id) DO UPDATE SET
                     rating=EXCLUDED.rating, review_count=EXCLUDED.review_count,
                     is_closed=EXCLUDED.is_closed, collected_at=NOW(),
                     raw_data=EXCLUDED.raw_data
                   RETURNING id""",
                (
                    str(uuid.uuid4()), ext_id,
                    r.get("name"), category, neighborhood,
                    r.get("full_address") or r.get("address"),
                    lat, lon,
                    r.get("overall_rating"), r.get("reviews_count"),
                    r.get("price_range"), bool(r.get("is_closed")),
                    json.dumps(r),
                ),
            )
            row = cur.fetchone()
            conn.commit()
            upserted += 1

            if do_embed and row:
                vec = embed_text(content)
                if vec:
                    store_embedding(conn, "businesses", str(row[0]),
                                    neighborhood, "economy", content, vec)
                    embedded += 1

    log.info(f"  Yelp: {upserted} upserted, {embedded} embedded")
    return collected, upserted, embedded


# ── Source: Google Maps reviews ───────────────────────────────────────────────

async def collect_google_maps(conn, run_id: str, do_embed: bool) -> tuple[int, int, int]:
    log.info("Collecting Google Maps reviews for Montgomery, AL...")
    collected = upserted = embedded = 0

    # GMaps dataset = URL-based (filter-based retourne no_records_found).
    # On passe des URLs de recherche Google Maps pour Montgomery, AL.
    GMAPS_DATASET_ID = "gd_luzfs1dn2oa0teb81"
    mgm_coords = "32.3792,-86.3077,13z"
    gmaps_urls = [
        {"url": f"https://www.google.com/maps/search/restaurants/@{mgm_coords}"},
        {"url": f"https://www.google.com/maps/search/shops/@{mgm_coords}"},
        {"url": f"https://www.google.com/maps/search/services/@{mgm_coords}"},
        {"url": f"https://www.google.com/maps/search/parks/@{mgm_coords}"},
        {"url": f"https://www.google.com/maps/search/healthcare/@{mgm_coords}"},
    ]
    trigger_resp = requests.post(
        f"https://api.brightdata.com/datasets/v3/trigger?dataset_id={GMAPS_DATASET_ID}&include_errors=true",
        headers={"Authorization": f"Bearer {BRIGHT_DATA_TOKEN}", "Content-Type": "application/json"},
        json=gmaps_urls,
        timeout=30,
    )
    trigger_data = trigger_resp.json()
    snapshot_id = trigger_data.get("snapshot_id")
    if not snapshot_id:
        log.error(f"  GMaps trigger failed: {trigger_data}")
        return 0, 0, 0
    log.info(f"  GMaps snapshot: {snapshot_id} — waiting...")
    records = brightdata_download(snapshot_id)

    log.info(f"  Got {len(records)} Google Maps records")
    collected = len(records)

    for r in records:
        ext_id = str(r.get("review_id") or uuid.uuid4())
        place_addr = r.get("address") or ""
        neighborhood = "Montgomery"
        # Try to extract neighborhood from address
        for part in str(place_addr).split(","):
            part = part.strip()
            if part and part not in ("Montgomery", "AL", "Alabama", "USA", "United States"):
                neighborhood = part
                break

        content = (
            f"{r.get('place_name', '')} in {neighborhood}: "
            f"{str(r.get('review', ''))[:300]}"
        )

        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO civic_data.reviews
                   (id, source, external_id, place_name, place_address,
                    neighborhood, rating, review_text, review_date, raw_data, collected_at)
                   VALUES (%s,'google_maps',%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                   ON CONFLICT (source, external_id) DO NOTHING
                   RETURNING id""",
                (
                    str(uuid.uuid4()), ext_id,
                    r.get("place_name"), place_addr, neighborhood,
                    r.get("review_rating"), r.get("review"),
                    r.get("review_date"), json.dumps(r),
                ),
            )
            row = cur.fetchone()
            conn.commit()
            if row:
                upserted += 1
                if do_embed:
                    vec = embed_text(content)
                    if vec:
                        store_embedding(conn, "reviews", str(row[0]),
                                        neighborhood, "governance", content, vec)
                        embedded += 1

    log.info(f"  Google Maps: {upserted} upserted, {embedded} embedded")
    return collected, upserted, embedded


# ── Source: Indeed jobs ───────────────────────────────────────────────────────

async def collect_indeed(conn, run_id: str, do_embed: bool) -> tuple[int, int, int]:
    log.info("Collecting Indeed jobs for Montgomery, AL...")
    collected = upserted = embedded = 0

    # BUG-024: dataset Indeed = URL-based, pas filter-based. Requiert "url" Indeed.
    # gd_lpfll7v5hcqtkxl6l = LinkedIn (erreur Gemini). Notre vrai Indeed = gd_l4dx9j9sscpvs7no2
    INDEED_DATASET_ID = "gd_l4dx9j9sscpvs7no2"
    indeed_url = "https://www.indeed.com/jobs?l=Montgomery%2C+AL&radius=25"
    trigger_resp = requests.post(
        f"https://api.brightdata.com/datasets/v3/trigger?dataset_id={INDEED_DATASET_ID}&include_errors=true",
        headers={"Authorization": f"Bearer {BRIGHT_DATA_TOKEN}", "Content-Type": "application/json"},
        json=[{"url": indeed_url}],
        timeout=30,
    )
    trigger_data = trigger_resp.json()
    snapshot_id = trigger_data.get("snapshot_id")
    if not snapshot_id:
        log.error(f"  Indeed trigger failed: {trigger_data}")
        return 0, 0, 0
    log.info(f"  Indeed snapshot: {snapshot_id} — waiting...")
    records = brightdata_download(snapshot_id)

    log.info(f"  Got {len(records)} Indeed records")
    collected = len(records)

    for r in records:
        ext_id = str(r.get("job_id") or r.get("id") or r.get("url") or uuid.uuid4())

        salary_raw = r.get("salary") or {}
        sal_min = salary_raw.get("min") if isinstance(salary_raw, dict) else None
        sal_max = salary_raw.get("max") if isinstance(salary_raw, dict) else None
        sal_type = salary_raw.get("type") if isinstance(salary_raw, dict) else None

        content = (
            f"{r.get('job_title', r.get('title', ''))} at "
            f"{r.get('company_name', r.get('company', ''))} in Montgomery AL"
            + (f" — ${sal_min}-{sal_max}/{sal_type}" if sal_min else "")
        )

        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO civic_data.jobs
                   (id, source, external_id, title, company,
                    neighborhood, salary_min, salary_max, salary_type,
                    raw_data, collected_at)
                   VALUES (%s,'indeed',%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                   ON CONFLICT (source, external_id) DO UPDATE SET
                     salary_min=EXCLUDED.salary_min, salary_max=EXCLUDED.salary_max,
                     collected_at=NOW(), raw_data=EXCLUDED.raw_data
                   RETURNING id""",
                (
                    str(uuid.uuid4()), ext_id,
                    r.get("job_title") or r.get("title"),
                    r.get("company_name") or r.get("company"),
                    "Montgomery", sal_min, sal_max, sal_type,
                    json.dumps(r),
                ),
            )
            row = cur.fetchone()
            conn.commit()
            upserted += 1

            if do_embed and row:
                vec = embed_text(content)
                if vec:
                    store_embedding(conn, "jobs", str(row[0]),
                                    "Montgomery", "economy", content, vec)
                    embedded += 1

    log.info(f"  Indeed: {upserted} upserted, {embedded} embedded")
    return collected, upserted, embedded


# ── Source: Census ACS ────────────────────────────────────────────────────────

def collect_census(conn, run_id: str) -> tuple[int, int, int]:
    """
    Fetch Census ACS 5-year estimates for all Montgomery County tracts.
    Populates civic_data.census + civic_data.neighborhoods.
    Real tract IDs from Census API — no hardcoding.
    """
    log.info("Collecting Census ACS data for Montgomery County, AL...")
    collected = upserted = 0
    vars_str = ",".join(["NAME"] + list(CENSUS_VARS.values()))

    for year in CENSUS_YEARS:
        # ACS 5-year data available from 2009 onward
        url = (
            f"https://api.census.gov/data/{year}/acs/acs5"
            f"?get={vars_str}"
            f"&for=tract:*"
            f"&in=state:{CENSUS_STATE}%20county:{CENSUS_COUNTY}"
        )
        try:
            r = requests.get(url, timeout=30)
            if r.status_code != 200:
                log.warning(f"  Census {year}: HTTP {r.status_code} — skipping")
                continue

            rows = r.json()
            header = rows[0]
            data_rows = rows[1:]
            log.info(f"  Census {year}: {len(data_rows)} tracts")

            for row in data_rows:
                record = dict(zip(header, row))
                tract_id = record.get("tract", "")
                tract_name = record.get("NAME", "")

                # Register neighborhood from tract name
                # Census NAME format: "Census Tract X, Montgomery County, Alabama"
                neighborhood = tract_name.split(",")[0].replace("Census Tract ", "Tract ")
                upsert_neighborhood(conn, neighborhood, tract_id)

                for metric_name, census_code in CENSUS_VARS.items():
                    raw_val = record.get(census_code)
                    try:
                        val = float(raw_val) if raw_val not in (None, "-1", "-666666666") else None
                    except (ValueError, TypeError):
                        val = None

                    if val is None:
                        continue

                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO civic_data.census
                               (id, census_tract, neighborhood, year, metric, value, collected_at)
                               VALUES (%s, %s, %s, %s, %s, %s, NOW())
                               ON CONFLICT (census_tract, year, metric) DO UPDATE
                               SET value=EXCLUDED.value, collected_at=NOW()""",
                            (str(uuid.uuid4()), tract_id, neighborhood, year, metric_name, val),
                        )
                    collected += 1
                    upserted += 1

            conn.commit()
            time.sleep(0.5)  # be polite to Census API

        except Exception as e:
            log.error(f"  Census {year} error: {e}")
            continue

    log.info(f"  Census: {upserted} rows upserted across {len(CENSUS_YEARS)} years")
    return collected, upserted, 0


# ── Main ──────────────────────────────────────────────────────────────────────

SOURCES = {
    "zillow":      ("async", collect_zillow),
    "yelp":        ("async", collect_yelp),
    "google_maps": ("async", collect_google_maps),
    "indeed":      ("async", collect_indeed),
    "census":      ("sync",  collect_census),
}


async def run_async_source(name, fn, conn, run_id, do_embed):
    try:
        return await fn(conn, run_id, do_embed)
    except Exception as e:
        log.error(f"{name} failed: {e}")
        return 0, 0, 0


def main():
    parser = argparse.ArgumentParser(description="Momentum MGM — Data Lake Collector")
    parser.add_argument("--source", default="all",
                        choices=list(SOURCES.keys()) + ["all"],
                        help="Data source to collect")
    parser.add_argument("--embed", action="store_true",
                        help="Generate pgvector embeddings (requires Google API key)")
    args = parser.parse_args()

    targets = list(SOURCES.keys()) if args.source == "all" else [args.source]

    if args.embed and not GOOGLE_API_KEY:
        log.warning("--embed requested but GOOGLE_API_KEY not set — skipping embeddings")
        args.embed = False

    conn = get_conn()
    log.info(f"Connected to PostgreSQL — collecting: {targets}")

    for name in targets:
        kind, fn = SOURCES[name]
        run_id = log_run_start(conn, name)
        log.info(f"\n{'='*50}\n[{name.upper()}]\n{'='*50}")

        try:
            if kind == "async":
                collected, upserted, embedded = asyncio.run(
                    run_async_source(name, fn, conn, run_id, args.embed)
                )
            else:
                collected, upserted, embedded = fn(conn, run_id)

            log_run_end(conn, run_id, collected, upserted, embedded)
            log.info(f"[{name}] Done — {collected} collected, {upserted} upserted, {embedded} embedded")

        except Exception as e:
            log.error(f"[{name}] Fatal: {e}")
            log_run_end(conn, run_id, 0, 0, 0, error=str(e))

    conn.close()
    log.info("\nAll sources complete.")


if __name__ == "__main__":
    main()
