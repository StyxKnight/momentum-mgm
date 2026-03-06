-- Momentum MGM — Civic Data Lake Schema
-- Run once: psql -U nodebb -d momentum -h 127.0.0.1 -f database/002_civic_data_lake.sql

CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS civic_data;

-- ── Neighborhoods reference ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS civic_data.neighborhoods (
    census_tract    VARCHAR PRIMARY KEY,
    name            VARCHAR NOT NULL,
    district        VARCHAR,
    notes           TEXT
);

-- ── Properties (Zillow) ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS civic_data.properties (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR DEFAULT 'zillow',
    external_id     VARCHAR,
    address         TEXT,
    neighborhood    VARCHAR,
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
    embedding       vector(3072),
    UNIQUE(source, external_id)
);

-- ── Businesses (Yelp) ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS civic_data.businesses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR DEFAULT 'yelp',
    external_id     VARCHAR,
    name            VARCHAR,
    category        VARCHAR,
    neighborhood    VARCHAR,
    address         TEXT,
    latitude        FLOAT,
    longitude       FLOAT,
    rating          FLOAT,
    review_count    INTEGER,
    price_range     VARCHAR,
    is_closed       BOOLEAN DEFAULT FALSE,
    raw_data        JSONB,
    collected_at    TIMESTAMP DEFAULT NOW(),
    embedding       vector(3072),
    UNIQUE(source, external_id)
);

-- ── Reviews (Google Maps + Yelp) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS civic_data.reviews (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR,
    external_id     VARCHAR,
    place_name      VARCHAR,
    place_address   TEXT,
    neighborhood    VARCHAR,
    rating          FLOAT,
    review_text     TEXT,
    review_date     DATE,
    civic_category  VARCHAR,
    raw_data        JSONB,
    collected_at    TIMESTAMP DEFAULT NOW(),
    embedding       vector(3072),
    UNIQUE(source, external_id)
);

-- ── Jobs (Indeed) ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS civic_data.jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR DEFAULT 'indeed',
    external_id     VARCHAR,
    title           VARCHAR,
    company         VARCHAR,
    neighborhood    VARCHAR,
    address         TEXT,
    salary_min      NUMERIC,
    salary_max      NUMERIC,
    salary_type     VARCHAR,
    posted_at       TIMESTAMP,
    raw_data        JSONB,
    collected_at    TIMESTAMP DEFAULT NOW(),
    embedding       vector(3072),
    UNIQUE(source, external_id)
);

-- ── Census historical data ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS civic_data.census (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    census_tract    VARCHAR,
    neighborhood    VARCHAR,
    year            INTEGER,
    metric          VARCHAR,
    value           FLOAT,
    margin_of_error FLOAT,
    collected_at    TIMESTAMP DEFAULT NOW(),
    UNIQUE(census_tract, year, metric)
);

-- ── Unified semantic index (cross-source pgvector) ───────────────────────────
CREATE TABLE IF NOT EXISTS civic_data.embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_table    VARCHAR NOT NULL,
    source_id       UUID NOT NULL,
    neighborhood    VARCHAR,
    civic_category  VARCHAR,
    content_text    TEXT NOT NULL,
    embedding       vector(3072) NOT NULL,
    embedded_at     TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS embeddings_vec_idx
    ON civic_data.embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);

-- ── Siphon audit trail ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS civic_data.siphon_runs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source            VARCHAR NOT NULL,
    records_collected INTEGER DEFAULT 0,
    records_upserted  INTEGER DEFAULT 0,
    records_embedded  INTEGER DEFAULT 0,
    status            VARCHAR DEFAULT 'running',
    error_message     TEXT,
    started_at        TIMESTAMP DEFAULT NOW(),
    completed_at      TIMESTAMP
);

-- ── City Open Data (code violations, permits, fire incidents) ────────────────
CREATE TABLE IF NOT EXISTS civic_data.city_data (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source       VARCHAR,        -- 'code_violations' | 'building_permits' | 'fire_incidents'
    category     VARCHAR,        -- civic category (10 catégories)
    neighborhood VARCHAR,
    address      TEXT,
    latitude     FLOAT,
    longitude    FLOAT,
    status       VARCHAR,
    reported_at  TIMESTAMP WITH TIME ZONE,
    raw_data     JSONB,
    collected_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_city_data_source       ON civic_data.city_data (source);
CREATE INDEX IF NOT EXISTS idx_city_data_neighborhood  ON civic_data.city_data (neighborhood);
CREATE INDEX IF NOT EXISTS idx_city_data_category      ON civic_data.city_data (category);
CREATE INDEX IF NOT EXISTS idx_city_data_reported_at   ON civic_data.city_data (reported_at);
CREATE INDEX IF NOT EXISTS idx_city_data_raw_objectid  ON civic_data.city_data ((raw_data->>'OBJECTID'));
-- Populated by: lake.py --source montgomery_opendata (refresh: siphon.py daily)
-- ArcGIS REST FeatureServer: services7.arcgis.com/xNUwUjOJqYE54USz (public, no auth)
--   Code_Violations_view       → housing        (~10k rows)
--   Building_Permit_viewlayer  → infrastructure (~5.6k rows, 2022+)
--   Fire_Rescue_All_Incidents  → public_safety  (~10k most recent of 55k total)

-- ── Neighborhoods populated dynamically by lake.py ──────────────────────────
-- DO NOT seed manually — neighborhood names come from Nominatim reverse geocoding
-- (lat/lon → suburb name). Census tract IDs come from Census API responses.
-- Montgomery County AL has 71 real tracts (1–61 with subdivisions like 22.01, 22.02).
-- Real tract numbers confirmed via Census API: state=01, county=101.
-- lake.py --source census populates this table with verified data.
