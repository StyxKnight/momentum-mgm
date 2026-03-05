# Data Layer — Momentum MGM

## Overview

Two databases, two purposes:

| Database | Schema | Purpose |
|---|---|---|
| `momentum` (PostgreSQL) | `public` | Decidim — proposals, votes, users, processes (managed by Rails migrations) |
| `momentum` (PostgreSQL) | `civic_data` | Data lake — Bright Data + Census + city open data + pgvector embeddings |

Both live on the same PostgreSQL 15 instance at `127.0.0.1:5432`.

---

## Decidim Schema (`public`)

Managed entirely by Decidim Rails migrations. Do not touch directly.

Key tables:

| Table | Purpose |
|---|---|
| `decidim_organizations` | Platform org (name, host, locales) |
| `decidim_participatory_processes` | 10 civic processes (one per category) |
| `decidim_components` | Components per process (proposals, votes) |
| `decidim_proposals_proposals` | Citizen proposals (title, body, published_at) |
| `decidim_proposals_proposal_votes` | Votes on proposals |
| `decidim_coauthorships` | Author links (proposal → user) |
| `decidim_users` | Citizens + admin accounts |

GraphQL API at `https://mgm.styxcore.dev/api` — public read-only.
Write operations via Rails runner only (no GraphQL mutations in 0.31).

---

## Civic Data Lake Schema (`civic_data`)

See full schema and documentation: **[docs/data_lake.md](data_lake.md)**

### Tables

| Table | Source | Records (est.) | Refresh |
|---|---|---|---|
| `civic_data.properties` | Zillow (Bright Data) | ~500 | monthly |
| `civic_data.businesses` | Yelp (Bright Data) | ~1000 | weekly |
| `civic_data.reviews` | Google Maps + Yelp (Bright Data) | ~3000 | weekly |
| `civic_data.jobs` | Indeed (Bright Data) | ~200 | daily |
| `civic_data.census` | US Census ACS API | ~340 rows/yr × 14 yrs | yearly |
| `civic_data.city_data` | opendata.montgomeryal.gov | variable | weekly |
| `civic_data.embeddings` | pgvector (OpenAI embeddings) | all records | on insert |
| `civic_data.neighborhoods` | TIGER / Montgomery GIS | 10-15 tracts | static |
| `civic_data.siphon_runs` | Internal audit trail | per run | always |

### Migration

```bash
# Run once to create civic_data schema
psql -U nodebb -d momentum -h 127.0.0.1 -f database/002_civic_data_lake.sql
```

---

## Migrations

| File | Purpose | When to run |
|---|---|---|
| `database/002_civic_data_lake.sql` | Create civic_data schema + all tables + pgvector index | Once, before lake.py |

Decidim migrations are handled by Rails: `bundle exec rails db:migrate`

---

## Seeding & Collection

| Script | Purpose | Run |
|---|---|---|
| `seeder/scrape.py` | Scrape montgomeryal.gov → 4 JSON files | Once (context for proposals) |
| `seeder/seed.py` | Generate + insert 60 proposals into Decidim | Once |
| `seeder/lake.py` | Initial data lake collection (all sources) | Once per source |
| `seeder/siphon.py` | Incremental refresh, called by systemd timer | Daily (automated) |

---

## pgvector

Extension already installed (used by RPG Forum project on same instance).

```sql
CREATE EXTENSION IF NOT EXISTS vector;
-- Index on embeddings table for cosine similarity search
CREATE INDEX ON civic_data.embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

Embedding model: `text-embedding-3-small` (OpenAI, 1536 dimensions).
Used for: semantic search across all civic data sources via MCP `semantic_civic_search` tool.

---

## Neighborhood Reference

Montgomery, AL — census tracts → neighborhood names.
Authoritative source: US Census TIGER 2020 + Montgomery Planning GIS.
Stored in `civic_data.neighborhoods`, seeded by `lake.py --source neighborhoods`.

Neighborhood names used consistently across ALL tables as the linking key between sources.

---

*Last updated: 2026-03-05*
