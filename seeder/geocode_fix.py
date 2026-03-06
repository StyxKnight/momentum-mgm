"""
geocode_fix.py — Fix neighborhood fields in civic_data tables.

Strategy:
  properties  → zip code (raw_data->>'zipcode') → neighborhood name
  businesses  → extract zip from address text  → neighborhood name (only "Montgomery" records)
  census      → census tract number            → neighborhood zone

Montgomery AL zip → neighborhood mapping (verified from Zillow dataset distribution):
  36104  Downtown Montgomery
  36105  South Montgomery
  36106  Midtown / Cloverdale
  36107  Cottage Hill
  36108  West Side
  36109  East Montgomery / Forest Park
  36110  North Montgomery / Chisholm
  36111  Southeast Montgomery
  36116  South Montgomery / Eastchase
  36117  East Montgomery / Eastdale
"""

import os
import re
import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

DB_URL = os.environ.get("DATABASE_URL",
    "postgresql://nodebb:superSecret123@localhost:5432/momentum")

# ── zip → neighborhood ───────────────────────────────────────────────────────

ZIP_TO_NEIGHBORHOOD = {
    "36104": "Downtown Montgomery",
    "36105": "South Montgomery",
    "36106": "Midtown / Cloverdale",
    "36107": "Cottage Hill",
    "36108": "West Side",
    "36109": "East Montgomery / Forest Park",
    "36110": "North Montgomery / Chisholm",
    "36111": "Southeast Montgomery",
    "36116": "South Montgomery / Eastchase",
    "36117": "East Montgomery / Eastdale",
}

# ── census tract → neighborhood zone ─────────────────────────────────────────
# Montgomery County AL census tracts (2020 Census, FIPS 01101)
# Mapped from geographic knowledge: urban core tracts 1-33, rural 51+

TRACT_TO_NEIGHBORHOOD = {
    # Downtown / Capitol area
    "000100": "Downtown Montgomery",
    "000200": "Downtown Montgomery",
    # Centennial Hill (historic Black neighborhood)
    "000300": "Centennial Hill",
    "000400": "Centennial Hill",
    # West Side (target of $36.6M federal access & equity grant)
    "000500": "West Side",
    "000600": "West Side",
    "000700": "West Side",
    "000900": "West Side",
    "001000": "West Side",
    # Cottage Hill / Garden District (west-central)
    "001100": "Cottage Hill",
    "001200": "Cottage Hill",
    # Midtown / Cloverdale (historic affluent district)
    "001300": "Midtown / Cloverdale",
    "001400": "Midtown / Cloverdale",
    # East Montgomery / Forest Park
    "001500": "East Montgomery / Forest Park",
    "001600": "East Montgomery / Forest Park",
    "001700": "East Montgomery / Forest Park",
    # South Montgomery / Dalraida
    "001800": "South Montgomery",
    "001900": "South Montgomery",
    "002000": "South Montgomery",
    # Southeast Montgomery
    "002100": "Southeast Montgomery",
    # North Montgomery / Chisholm (north corridor)
    "002201": "North Montgomery / Chisholm",
    "002202": "North Montgomery / Chisholm",
    "002300": "North Montgomery / Chisholm",
    "002400": "North Montgomery / Chisholm",
    # East Montgomery / Vaughn / Carmichael
    "002500": "East Montgomery / Forest Park",
    "002600": "East Montgomery / Vaughn",
    # East Montgomery / Eastdale
    "002700": "East Montgomery / Eastdale",
    "002800": "East Montgomery / Eastdale",
    "002900": "East Montgomery / Eastdale",
    "002901": "East Montgomery / Eastdale",
    "002902": "East Montgomery / Eastdale",
    # Southeast Montgomery
    "003000": "Southeast Montgomery",
    "003100": "Southeast Montgomery",
    "003200": "Southeast Montgomery",
    # Pike Road / East fringe
    "003301": "Pike Road",
    "003302": "Pike Road",
    "003303": "Pike Road",
    "003304": "Pike Road",
    # Rural / exurban Montgomery County
    "005101": "Northwest Montgomery County",
    "005102": "Northwest Montgomery County",
    "005301": "Rural Montgomery County",
    "005302": "Rural Montgomery County",
    "005402": "Rural Montgomery County",
    "005403": "Rural Montgomery County",
    "005406": "Rural Montgomery County",
    "005407": "Rural Montgomery County",
    "005408": "Rural Montgomery County",
    "005409": "Rural Montgomery County",
    "005410": "Rural Montgomery County",
    "005411": "Rural Montgomery County",
    "005412": "Rural Montgomery County",
    "005413": "Rural Montgomery County",
    "005414": "Rural Montgomery County",
    "005501": "Rural Montgomery County",
    "005502": "Rural Montgomery County",
    "005503": "Rural Montgomery County",
    "005504": "Rural Montgomery County",
    "005603": "Rural Montgomery County",
    "005604": "Rural Montgomery County",
    "005605": "Rural Montgomery County",
    "005606": "Rural Montgomery County",
    "005607": "Rural Montgomery County",
    "005608": "Rural Montgomery County",
    "005609": "Rural Montgomery County",
    "005610": "Rural Montgomery County",
    "005611": "Rural Montgomery County",
    "005612": "Rural Montgomery County",
    "005613": "Rural Montgomery County",
    "005614": "Rural Montgomery County",
    "005700": "Rural Montgomery County",
    "005800": "Rural Montgomery County",
    "005901": "Rural Montgomery County",
    "005902": "Rural Montgomery County",
    "005903": "Rural Montgomery County",
    "005904": "Rural Montgomery County",
    "006000": "Rural Montgomery County",
    "006100": "Rural Montgomery County",
}

ZIP_RE = re.compile(r'\b(3610[4-9]|3611[0-7])\b')


def extract_zip(address: str) -> str | None:
    m = ZIP_RE.search(address or "")
    return m.group(1) if m else None


def run():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # ── 1. Properties ────────────────────────────────────────────────────────
    print("\n[1] Fixing properties neighborhoods...")
    cur.execute("""
        SELECT id, raw_data->>'zipcode' AS zip
        FROM civic_data.properties
        WHERE raw_data->>'zipcode' IS NOT NULL
    """)
    rows = cur.fetchall()
    updated = 0
    skipped = 0
    for prop_id, zip_code in rows:
        neighborhood = ZIP_TO_NEIGHBORHOOD.get(zip_code)
        if neighborhood:
            cur.execute(
                "UPDATE civic_data.properties SET neighborhood = %s WHERE id = %s",
                (neighborhood, prop_id)
            )
            updated += 1
        else:
            skipped += 1
    conn.commit()
    print(f"  Properties: {updated} updated, {skipped} skipped (unknown zip)")

    # ── 2. Businesses (only "Montgomery" — keep Yelp-mapped ones) ────────────
    print("\n[2] Fixing businesses neighborhoods...")
    cur.execute("""
        SELECT id, address
        FROM civic_data.businesses
        WHERE neighborhood IN ('Montgomery', 'Montgomery County', '')
           OR neighborhood IS NULL
    """)
    rows = cur.fetchall()
    updated = 0
    skipped = 0
    for biz_id, address in rows:
        zip_code = extract_zip(address or "")
        neighborhood = ZIP_TO_NEIGHBORHOOD.get(zip_code) if zip_code else None
        if neighborhood:
            cur.execute(
                "UPDATE civic_data.businesses SET neighborhood = %s WHERE id = %s",
                (neighborhood, biz_id)
            )
            updated += 1
        else:
            skipped += 1
    conn.commit()
    print(f"  Businesses: {updated} updated, {skipped} skipped (no zip in address)")

    # ── 3. Census tracts ─────────────────────────────────────────────────────
    print("\n[3] Fixing census neighborhoods...")
    cur.execute("SELECT DISTINCT census_tract FROM civic_data.census")
    tracts = [r[0] for r in cur.fetchall()]
    updated = 0
    skipped = 0
    for tract in tracts:
        neighborhood = TRACT_TO_NEIGHBORHOOD.get(tract)
        if neighborhood:
            cur.execute(
                "UPDATE civic_data.census SET neighborhood = %s WHERE census_tract = %s",
                (neighborhood, tract)
            )
            updated += 1
        else:
            skipped += 1
            print(f"    WARN: no mapping for tract {tract}")
    conn.commit()
    print(f"  Census: {updated} tracts updated, {skipped} tracts skipped")

    # ── 4. Verification ──────────────────────────────────────────────────────
    print("\n[4] Verification:")
    for table in ("properties", "businesses"):
        cur.execute(f"""
            SELECT neighborhood, COUNT(*)
            FROM civic_data.{table}
            GROUP BY neighborhood
            ORDER BY COUNT(*) DESC
            LIMIT 15
        """)
        rows = cur.fetchall()
        print(f"\n  {table}:")
        for hood, count in rows:
            print(f"    {count:4d}  {hood}")

    cur.execute("""
        SELECT neighborhood, COUNT(DISTINCT census_tract) as tracts
        FROM civic_data.census
        GROUP BY neighborhood
        ORDER BY tracts DESC
        LIMIT 15
    """)
    rows = cur.fetchall()
    print("\n  census (by neighborhood zone):")
    for hood, tracts in rows:
        print(f"    {tracts:3d} tracts  {hood}")

    cur.close()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    run()
