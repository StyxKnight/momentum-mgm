# Data Lake — Momentum MGM Civic Intelligence

## Vision

The data lake transforms Momentum MGM from a participation platform into a **civic intelligence platform**. Instead of just showing current proposals, the admin bridge can now answer: *"What has been happening in West Montgomery over the past 10 years, what are citizens saying now, and where is this heading?"*

This is what serious smart city platforms do. Brasil Participativo classifies proposals. Barcelona Decidim shows participation stats. We do both — plus historical neighborhood intelligence.

---

## Architecture

```
EXTERNAL SOURCES                PIPELINE                    STORAGE
────────────────                ────────                    ───────

Bright Data Datasets:
  ZillowProperties   ─────┐
  YelpBusinesses     ─────┤
  YelpReviews        ─────┤──→ lake.py (initial load) ──→ PostgreSQL
  GoogleMapsReviews  ─────┤       + normalize               civic_data schema
  IndeedJobs         ─────┤       + geocode → neighborhood   + pgvector embeddings
  GlassdoorCompanies ─────┘       + embed

Census ACS API (free):
  2010–2024, by tract ──────────→ census ETL ────────────→ civic_data.census

City of Montgomery:
  opendata.montgomeryal.gov ────→ scrape.py (existing) ──→ JSON files (existing)
                                                            + civic_data tables

Decidim (live):
  proposals + votes ────────────→ GraphQL reads ─────────→ embeddings only
  (lives in momentum DB)                                    (source stays in Decidim)

                                REFRESH (siphon.py)
                                  systemd timer:
                                  Indeed     → daily
                                  Yelp/GMaps → weekly
                                  Zillow     → monthly
                                  Census ACS → yearly
```

---

## Data Sources

### Bright Data Datasets (SDK)

| Dataset | Class | Dataset ID | Fields used | Refresh |
|---|---|---|---|---|
| Zillow Properties | `ZillowProperties` | `gd_lfqkr8wm13ixtbd8f5` | address, price, vacancy, sqft, lat/lon | monthly |
| Yelp Businesses | `YelpBusinesses` | `gd_lgugwl0519h1p14rwk` | name, category, is_closed, rating, review_count, lat/lon | weekly |
| Yelp Reviews | `YelpReviews` | via SDK | business_id, rating, text, date | weekly |
| Google Maps Reviews | `GoogleMapsReviews` | `gd_luzfs1dn2oa0teb81` | place_name, address, rating, review, review_date | weekly | ⚠️ PARKED — dataset URL-based (place URLs requises), voir BUG-025 |
| Indeed Jobs | `IndeedJobs` | `gd_l4dx9j9sscpvs7no2` | title, company, salary, location, posted_at | daily | ⚠️ PARKED — dataset URL-based (/viewjob URLs requises), voir BUG-024 |

> **Bright Data réel collecté:** Zillow ✅ 500 props, Yelp ✅ 500 bizs. Google Maps et Indeed = 0 records (datasets URL-based incompatibles avec filtre géo). Voir bugs.md BUG-024/025.

All filtered to: **city = "Montgomery", state = "AL"** (or "Alabama")

### Census ACS (US Census Bureau API — free)

- **Endpoint:** `https://api.census.gov/data/{year}/acs/acs5`
- **Geography:** Census tract, Montgomery County, Alabama (FIPS: 01101)
- **Years:** 2010–2024 (5-year ACS estimates)
- **Variables per tract:**

| Variable | Census Code | Meaning |
|---|---|---|
| Median household income | B19013_001E | Economic status |
| Poverty rate | B17001_002E / B17001_001E | Deprivation |
| Housing vacancy rate | B25002_003E / B25002_001E | Blight risk |
| Unemployment rate | B23025_005E / B23025_002E | Economic activity |
| Population | B01001_001E | Size/density |
| Median gross rent | B25064_001E | Housing cost |
| % with bachelor's degree+ | B15003_022E+ / B15003_001E | Education |
| % owner-occupied housing | B25003_002E / B25003_001E | Stability |
| % white alone | B02001_002E / B02001_001E | Demographics |
| % Black/African American | B02001_003E / B02001_001E | Demographics |

### City of Montgomery ArcGIS Open Data (16 sources)

- **Portal:** ArcGIS REST API — `services7.arcgis.com/xNUwUjOJqYE54USz/ArcGIS/rest/services/`
- **Auth:** None required
- **All stored in:** `civic_data.city_data` (source + category + neighborhood + address + lat/lon + status + raw_data)

| Source | Category | Records |
|---|---|---|
| fire_incidents | public_safety | ~20,000 |
| code_violations | housing | ~10,000 |
| building_permits | housing | 5,619 |
| housing_condition | housing | 5,561 |
| transit_stops | transportation | 1,613 |
| food_safety | health | 1,337 |
| environmental_nuisance | environment | 330 |
| education_facilities | education | 97 |
| citizen_reports | governance | 16 |
| behavioral_centers | health | 13 |
| opportunity_zones | economy | 12 |
| infrastructure_projects | infrastructure | 10 |
| business_licenses (2022+) | economy | 12,751 |
| historic_markers | parks_culture | 319 |
| community_centers | parks_culture | 24 |
| education_facility | education | 114 |
| parks_recreation | parks_culture | 97 |
| city_owned_property | governance | 681 |
| zoning_decisions | governance | 2,005 |
| **TOTAL** | | **~60,600** |

---

## Database Schema

Schema: `civic_data` (separate from Decidim's `public` schema in `momentum` DB)

```sql
-- Enable pgvector (already installed)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS civic_data;

-- ── Properties (Zillow) ──────────────────────────────────────────────────────
CREATE TABLE civic_data.properties (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR DEFAULT 'zillow',
    address         TEXT,
    neighborhood    VARCHAR,
    census_tract    VARCHAR,
    latitude        FLOAT,
    longitude       FLOAT,
    price           NUMERIC,
    price_per_sqft  NUMERIC,
    sqft            INTEGER,
    bedrooms        INTEGER,
    bathrooms       NUMERIC,
    property_type   VARCHAR,
    days_on_market  INTEGER,
    is_vacant       BOOLEAN,
    raw_data        JSONB,
    collected_at    TIMESTAMP DEFAULT NOW(),
    embedding       vector(1536)
);

-- ── Businesses (Yelp) ────────────────────────────────────────────────────────
CREATE TABLE civic_data.businesses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR DEFAULT 'yelp',
    external_id     VARCHAR,
    name            VARCHAR,
    category        VARCHAR,
    neighborhood    VARCHAR,
    census_tract    VARCHAR,
    address         TEXT,
    latitude        FLOAT,
    longitude       FLOAT,
    rating          FLOAT,
    review_count    INTEGER,
    price_range     VARCHAR,
    is_closed       BOOLEAN DEFAULT FALSE,
    raw_data        JSONB,
    collected_at    TIMESTAMP DEFAULT NOW(),
    embedding       vector(1536),
    UNIQUE(source, external_id)
);

-- ── Reviews (Google Maps + Yelp) ─────────────────────────────────────────────
CREATE TABLE civic_data.reviews (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR,        -- 'google_maps' | 'yelp'
    place_name      VARCHAR,
    place_address   TEXT,
    neighborhood    VARCHAR,
    rating          FLOAT,
    review_text     TEXT,
    review_date     DATE,
    category        VARCHAR,        -- inferred civic category
    raw_data        JSONB,
    collected_at    TIMESTAMP DEFAULT NOW(),
    embedding       vector(1536)
);

-- ── Jobs (Indeed) ────────────────────────────────────────────────────────────
CREATE TABLE civic_data.jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR DEFAULT 'indeed',
    title           VARCHAR,
    company         VARCHAR,
    neighborhood    VARCHAR,
    address         TEXT,
    salary_min      NUMERIC,
    salary_max      NUMERIC,
    salary_type     VARCHAR,        -- 'hourly' | 'annual'
    posted_at       TIMESTAMP,
    raw_data        JSONB,
    collected_at    TIMESTAMP DEFAULT NOW(),
    embedding       vector(1536)
);

-- ── Census Historical Data ───────────────────────────────────────────────────
CREATE TABLE civic_data.census (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    census_tract    VARCHAR,
    neighborhood    VARCHAR,        -- human-readable name
    year            INTEGER,
    metric          VARCHAR,        -- e.g. 'median_income', 'poverty_rate'
    value           FLOAT,
    margin_of_error FLOAT,
    collected_at    TIMESTAMP DEFAULT NOW(),
    UNIQUE(census_tract, year, metric)
);

-- ── City Open Data (311, crime) ──────────────────────────────────────────────
CREATE TABLE civic_data.city_data (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR,        -- '311' | 'crime' | 'permits'
    category        VARCHAR,
    neighborhood    VARCHAR,
    address         TEXT,
    latitude        FLOAT,
    longitude       FLOAT,
    status          VARCHAR,
    reported_at     TIMESTAMP,
    raw_data        JSONB,
    collected_at    TIMESTAMP DEFAULT NOW(),
    embedding       vector(1536)
);

-- ── Unified Embedding Index ──────────────────────────────────────────────────
-- Cross-source semantic search — points to any record in any table
CREATE TABLE civic_data.embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_table    VARCHAR,        -- 'properties' | 'businesses' | 'reviews' | 'jobs' | 'census' | 'proposal'
    source_id       UUID,           -- FK to the source record
    neighborhood    VARCHAR,
    category        VARCHAR,        -- civic category (our 10)
    content_text    TEXT,           -- what was embedded
    embedding       vector(1536),
    embedded_at     TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ON civic_data.embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ── Siphon Audit Trail ───────────────────────────────────────────────────────
CREATE TABLE civic_data.siphon_runs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source            VARCHAR,
    records_collected INTEGER DEFAULT 0,
    records_upserted  INTEGER DEFAULT 0,
    records_embedded  INTEGER DEFAULT 0,
    status            VARCHAR,       -- 'running' | 'success' | 'error'
    error_message     TEXT,
    started_at        TIMESTAMP DEFAULT NOW(),
    completed_at      TIMESTAMP
);

-- ── Montgomery Neighborhoods Reference ──────────────────────────────────────
-- Maps census tracts to human-readable neighborhood names
CREATE TABLE civic_data.neighborhoods (
    census_tract    VARCHAR PRIMARY KEY,
    name            VARCHAR NOT NULL,
    district        VARCHAR,        -- city council district
    area_sqmi       FLOAT,
    notes           TEXT
);
```

---

## Files

```
momentum-mgm/
├── database/
│   └── 002_civic_data_lake.sql     ← schema above (run once)
├── seeder/
│   ├── lake.py                     ← initial full collection (run once per source)
│   └── siphon.py                   ← incremental refresh (run by systemd timer)
└── systemd/
    ├── momentum-lake.service        ← runs siphon.py
    └── momentum-lake.timer          ← schedule: daily/weekly/monthly
```

---

## lake.py — Initial Collection

Single script, run once to populate each source:

```
python lake.py --source zillow      # ~500 Montgomery properties
python lake.py --source yelp        # ~1000 Montgomery businesses
python lake.py --source google_maps # Reviews of key city locations
python lake.py --source indeed      # Active job listings
python lake.py --source census      # 2010-2024 ACS by tract
python lake.py --source all         # Everything
```

Pipeline per source:
1. Pull from Bright Data SDK (async, with retry)
2. Filter to Montgomery, AL
3. Normalize fields → standard schema
4. Geocode → neighborhood (Nominatim reverse geocoding, cached)
5. Upsert into PostgreSQL (ON CONFLICT DO UPDATE)
6. Embed content text → pgvector
7. Log to `siphon_runs`

---

## siphon.py — Incremental Refresh

Called by systemd timer. Smart refresh:
- Checks `siphon_runs` for last successful run per source
- Only collects records newer than last run
- Skips source if last run < threshold (e.g., Zillow: skip if < 25 days ago)
- Alerts on failure (logs to file, future: Decidim admin notification)

---

## systemd Timer

```ini
# momentum-lake.timer
[Unit]
Description=Momentum MGM Data Lake Siphon

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

siphon.py handles the per-source schedule logic internally (daily/weekly/monthly).

---

## Neighborhood Mapping

Montgomery census tracts → neighborhood names (initial seed, validated against city records):

| Census Tract | Neighborhood | District |
|---|---|---|
| 0001.00 | Downtown | District 1 |
| 0002.00 | Capitol Heights | District 2 |
| 0003.00 | Old Cloverdale | District 3 |
| 0004.00 | Cloverdale | District 3 |
| 0005.00 | Garden District | District 4 |
| 0006.00 | Dalraida | District 5 |
| 0007.00 | Midtown | District 2 |
| 0008.00 | West Montgomery | District 6 |
| 0009.00 | Chisholm | District 7 |
| 0010.00 | East Montgomery | District 5 |

> Note: Exact tract-to-neighborhood mapping validated against US Census TIGER boundaries and Montgomery Planning GIS. Update before demo.

---

## New MCP Tools (added to server.py)

### Tool 7 — get_neighborhood_intelligence(neighborhood)
```
Input:  neighborhood name (e.g. "West Montgomery")
Output: {
  census_trend: {income, poverty, vacancy} over 2010-2024,
  real_estate:  current median price, vacancy rate, trend,
  businesses:   count active, count closed YTD, top categories,
  jobs:         active listings, top employers, salary range,
  proposals:    current Decidim proposals for this neighborhood,
  risk_score:   composite civic health score (0-100),
  ai_summary:   Claude-generated narrative + recommendation
}
```

### Tool 8 — semantic_civic_search(query, neighborhood=None)
```
Input:  natural language query + optional neighborhood filter
Output: top 10 semantically relevant records across ALL sources
        (proposals + properties + businesses + reviews + census)
        Each result includes source, neighborhood, date, relevance score
```

### Tool 9 — get_neighborhood_velocity(neighborhood=None)
```
Input:  neighborhood name (optional — if None, returns all neighborhoods ranked)
Output: {
  neighborhood: "West Montgomery",
  health_score_current: 45,          ← current composite score
  velocity: -8.2,                     ← points/year (positive=improving, negative=declining)
  trend: "accelerating_decline",      ← accelerating_decline | decelerating_decline |
                                          stable | decelerating_growth | accelerating_growth
  metric_velocities: {
    median_income:    -2.1%/yr,
    vacancy_rate:     +3.4%/yr,
    business_closures: +1.8%/yr,
    job_postings:     -0.9%/yr,
    proposal_volume:  +2.3%/yr       ← citizens escalating concerns
  },
  projection_2yr:   32,              ← estimated score in 2 years if trend continues
  urgency:          "critical",      ← critical | high | medium | low | monitor
  recommendation:   "Immediate intervention recommended..."
}
```

Computed via linear regression on Census ACS 2010-2024 + Bright Data refresh.
Cross-referenced with Decidim proposal volume trend — rising proposals = citizens sensing deterioration before metrics catch up.

### Tool 10 — find_solutions(problem, neighborhood, budget_constraint=True)
```
Input:  problem description (free text or structured from velocity output)
        neighborhood name
        budget_constraint: bool (default True — only realistic options)

Output: {
  problem_summary:    "West Montgomery: housing vacancy +31%, income -18% over 10yr",
  federal_programs: [
    { name: "HUD Choice Neighborhoods", eligible: true, amount: "up to $30M",
      deadline: "2026-06-01", fit_score: 0.91 },
    { name: "CDBG Entitlement Grant", eligible: true, amount: "$2-5M/yr",
      deadline: "ongoing", fit_score: 0.87 },
    ...
  ],
  comparable_cities: [
    { city: "Birmingham AL", problem: "similar vacancy 2018",
      solution: "Land bank + rehab program", outcome: "-18% vacancy in 3yr" },
    ...
  ],
  montgomery_specific: [
    "Aligns with Housing & Neighborhoods civic category (blight, vacancy)",
    "Public Works Dept has active blight removal budget FY2026",
    "12 active citizen proposals on this topic (Decidim)"
  ],
  recommended_actions: [
    { action: "...", feasibility: "high", impact: "high", timeline: "6mo",
      cost_estimate: "$X", funding_source: "CDBG" },
    ...
  ],
  total_estimated_cost: "$2.4M",
  federal_fundable_pct: "70%",
  urgency_note: "Velocity at -8.2/yr — window for intervention: 18 months"
}
```

Sources queried at call time (live, not pre-cached):
- HUD grants database (grants.gov) via OpenRouter web search
- What comparable Alabama/Southern cities did in similar situations
- Montgomery FY2026 budget (Open Finance portal)
- Active Decidim proposals for context + citizen voice
- Civic category alignment (our 10 categories → maps to city departments + 311)

This closes the full governance loop:
**detect** (velocity) → **understand** (intelligence) → **find solutions** → **act**

---

## Civic Health Score

Composite score (0–100) per neighborhood, computed from:

| Indicator | Weight | Source |
|---|---|---|
| Income trend (10yr) | 20% | Census ACS |
| Housing vacancy rate | 20% | Census + Zillow |
| Business closure rate | 15% | Yelp |
| Active job postings | 15% | Indeed |
| Crime / 311 density | 15% | City open data |
| Citizen proposal urgency | 15% | Decidim votes |

Higher = healthier. Enables: "show me the 3 most at-risk neighborhoods right now."

---

## Embeddings Strategy

Content text embedded per record type:

| Source | Embedded text |
|---|---|
| Property | `"{address} — {property_type}, {bedrooms}bd/{bathrooms}ba, ${price}, {days_on_market} days on market, {neighborhood}"` |
| Business | `"{name} ({category}) in {neighborhood} — rating {rating}/5, {review_count} reviews, {'closed' if is_closed else 'open'}"` |
| Review | `"{place_name} in {neighborhood}: {review_text}"` |
| Job | `"{title} at {company} in {neighborhood or 'Montgomery'} — ${salary_min}-${salary_max}"` |
| Census | `"{neighborhood} in {year}: median income ${value}, poverty {pov}%, vacancy {vac}%"` |
| Proposal | `"{title}: {body[:200]}"` (from Decidim, embedded at query time) |

Embedding model: `gemini-embedding-001` via Google GenAI API (3072 dimensions, Matryoshka). Voir DECISION-001 dans architecture.md.

---

## Cost Estimate

| Source | Records | Bright Data cost | Embed cost | Total |
|---|---|---|---|---|
| Zillow | ~500 | ~$1.25 | ~$0.01 | ~$1.26 |
| Yelp businesses | ~1000 | ~$2.50 | ~$0.02 | ~$2.52 |
| Yelp reviews | ~2000 | ~$5.00 | ~$0.04 | ~$5.04 |
| Google Maps | 0 ⚠️ parked | $0 | $0 | $0 |
| Indeed | 0 ⚠️ parked | $0 | $0 | $0 |
| Census ACS | 11,334 rows | FREE | ~$0.001 | ~$0.001 |
| **Total réel collecté** | | | | **~$4** |
| Monthly refresh (Zillow+Yelp) | | | | **~$2/month** |

> Bright Data 30-day trial. Google Maps + Indeed parked (BUG-024/025) — si débloqués, ajouter ~$3 initial + ~$2/month.

---

---

## Category Coverage — État réel ✅ COMPLÉTÉ (2026-03-07)

### Couverture actuelle — 10/10 catégories ✅

| Catégorie | Sources | Records |
|---|---|---|
| housing | code_violations + building_permits + housing_condition + Census | ~21,000+ |
| public_safety | fire_incidents | ~20,000 |
| economy | business_licenses (2022+) + opportunity_zones + Census income | ~12,763 |
| governance | citizen_reports + city_owned_property + zoning_decisions | ~2,702 |
| transportation | transit_stops | 1,613 |
| health | food_safety + behavioral_centers + Census | ~1,350 |
| education | education_facilities + education_facility + Census | ~211 |
| parks_culture | parks_recreation + historic_markers + community_centers | ~440 |
| environment | environmental_nuisance | 330 |
| infrastructure | infrastructure_projects + Census | ~10 |

> **Statut 2026-03-07:** Toutes les catégories ont une couverture minimale viable. Le plan ci-dessous a été exécuté — les sources Tier 1 ArcGIS sont toutes intégrées. Tier 2/3 = nice-to-have post-hackathon.

### Sources prioritaires à intégrer

#### Tier 1 — Impact maximal, accessible maintenant

**Montgomery Open Data Portal** (`opendata.montgomeryal.gov`)
- 311 Service Requests — incidents par quartier, type, temps de résolution → Infrastructure + Governance
- Crime incidents — par quartier, type, date → Public Safety
- Construction/building permits — → Housing + Infrastructure
- Code enforcement violations — logements insalubres par quartier → Housing

**Census ACS supplémentaire** (déjà le pipeline, juste ajouter les variables)
- `B08301` — Means of transportation to work → Transportation
- `B19083` — Gini coefficient → Economy (inégalité)
- `B25071` — Median gross rent as % of household income → Housing cost burden
- `B27001` — Health insurance coverage → Health

**Yelp — catégories manquantes** (même pipeline, élargir la recherche)
- Grocery stores, supermarkets → Environment (food deserts)
- Hospitals, urgent care, clinics → Health
- Schools, tutoring → Education
- Parks, recreation → Parks & Culture
- Bus stops (si Yelp les a) → Transportation

#### Tier 2 — Fort impact, requiert setup

**Bright Data — nouveaux datasets à scrapper**
- `Google Maps Places` (une fois BUG-025 résolu via Places API) — parcs, arrêts de bus, écoles, cliniques avec horaires et reviews
- `Zillow Rental Listings` — loyers actuels par quartier (complémente les ventes)
- `Apartment.com / Rent.com` — offre locative abordable
- `LinkedIn Job Postings` (via Bright Data) — emplois par industrie/quartier → Economy

**Sources gouvernementales gratuites**
- EPA AirNow API — qualité de l'air par zip code → Environment
- FEMA Flood Map Service Center API — zones inondables par adresse → Environment + Housing
- Alabama Report Card (`reportcard.alsde.edu`) — résultats scolaires par école → Education
- Bureau of Labor Statistics API — emploi par industrie, Montgomery MSA → Economy
- GTFS Montgomery MAX Bus — stops, routes, fréquences → Transportation

#### Tier 3 — Nice-to-have

- City Council meeting minutes (scraping montgomeryal.gov) → Governance
- USDA Food Access Research Atlas → Environment (food deserts officiels)
- HUD Fair Market Rents → Housing
- Glassdoor companies (Bright Data dataset déjà listé) → Economy

### Minimum Viable Coverage par catégorie

Pour que chaque MCP tool soit significatif, voici le minimum requis :

```
infrastructure:   Census + 311 requests + building permits
environment:      Census + Yelp groceries + EPA air + FEMA flood
housing:          Census + Zillow (geocoding fixé) + building permits + evictions
public_safety:    Census + crime incidents OpenData
transportation:   Census + GTFS MAX Bus stops/routes
health:           Census + Yelp clinics/hospitals + ACS health insurance
education:        Census + Yelp schools + AL Report Card
economy:          Census + Yelp businesses + Indeed jobs (quand fixé)
parks_culture:    Census + Yelp parks/museums + Google Maps (quand fixé)
governance:       Census + 311 + council minutes
```

### Fix prioritaire — Zillow geocoding

493/500 propriétés Zillow sont mappées à "Montgomery County" au lieu du quartier précis. Les lat/lon sont présents. Fix: passer chaque propriété par Nominatim reverse geocoding (1 req/sec) pour obtenir le `suburb` → mettre à jour `neighborhood`. ~8 minutes de processing sur les 500.

### Nouvelle table suggérée: `civic_data.incidents`

Pour les données 311 + crime + code violations — format unifié :

```sql
CREATE TABLE civic_data.incidents (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source        VARCHAR,          -- '311', 'crime', 'code_enforcement'
  incident_type VARCHAR,
  category      VARCHAR,          -- civic category (10 catégories)
  neighborhood  VARCHAR,
  latitude      FLOAT,
  longitude     FLOAT,
  reported_at   TIMESTAMP,
  resolved_at   TIMESTAMP,
  status        VARCHAR,
  raw_data      JSONB,
  collected_at  TIMESTAMP DEFAULT now()
);
```

### Embeddings backfill

- Passe 1: properties + businesses + city_data originale (44K) → ~48K embeddings
- Passe 2: 7 nouvelles sources ArcGIS (13,208 records) → en cours (log: `/tmp/embed_backfill2.log`)
- Modèle: `gemini-embedding-001` (3072d), rate: 0.05s/req (~20 req/s)
- Total estimé final: ~61K embeddings

*Last updated: 2026-03-07*
