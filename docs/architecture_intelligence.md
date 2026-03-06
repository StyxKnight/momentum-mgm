# Architecture Intelligence — Momentum MGM

## Conception finale (2026-03-06)

### Vision
Boucle complète: données réelles → analyse AI → rapport persistant → UI → conversation AI → solutions

---

## Flow

```
Données réelles
  (Census, Yelp, ArcGIS, Decidim, Zillow)
          ↓
  civic_data.* (PostgreSQL)
          ↓
  civic_intelligence.py  ← module partagé (logique pure)
       ↙        ↘
MCP server     Streamlit
(Claude/Grok)  (viewer)
       ↓
  Grok-4-Fast analyse
       ↓
  civic_data.reports (JSONB persistant)
       ↓
  Streamlit lit + affiche
       ↓
  Fonctionnaire/citoyen lit le rapport
       ↓
  Pose une question à Claude sur le rapport
       ↓
  Claude a le rapport comme contexte → find_solutions
       ↓
  Nouveau rapport sauvegardé → Streamlit affiche
```

---

## Module partagé: `civic_intelligence.py`

Logique extraite de `mcp-server/server.py`, importée par les deux frontends.

```python
# Fonctions pures — retournent des dicts Python
def get_neighborhood_velocity(neighborhood: str) -> dict
def get_neighborhood_intelligence(neighborhood: str) -> dict
def find_solutions(problem: str, neighborhood: str, report_context: dict = None) -> dict
def semantic_civic_search(query: str, neighborhood: str = None) -> list
```

### mcp-server/server.py
Devient un wrapper mince:
```python
from civic_intelligence import get_neighborhood_velocity
@mcp.tool()
def tool_velocity(neighborhood): return get_neighborhood_velocity(neighborhood)
```

### dashboard/dashboard.py
Appel direct:
```python
from civic_intelligence import get_neighborhood_velocity
data = get_neighborhood_velocity("West Side")
st.plotly_chart(velocity_chart(data))
```

---

## Table: civic_data.reports

```sql
CREATE TABLE civic_data.reports (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type  VARCHAR,      -- 'neighborhood_velocity' | 'neighborhood_intelligence' | 'find_solutions'
    subject      VARCHAR,      -- quartier ou problème
    generated_at TIMESTAMP DEFAULT NOW(),
    generated_by VARCHAR,      -- 'grok-4-fast' | 'claude-sonnet-4-6'
    payload      JSONB         -- rapport complet structuré
);
CREATE INDEX ON civic_data.reports (report_type, subject);
CREATE INDEX ON civic_data.reports (generated_at DESC);
```

### Payload schema par type

**neighborhood_velocity:**
```json
{
  "neighborhood": "West Side",
  "health_score_current": 45,
  "velocity": -8.2,
  "trend": "accelerating_decline",
  "metric_velocities": { "median_income": -2.1, "vacancy_rate": 3.4 },
  "projection_2yr": 32,
  "urgency": "critical"
}
```

**neighborhood_intelligence:**
```json
{
  "neighborhood": "West Side",
  "census_trend": { "income": [...], "poverty": [...] },
  "real_estate": { "median_price": 95000, "vacancy_rate": 18.2 },
  "businesses": { "count_active": 12, "top_categories": [...] },
  "city_data": { "code_violations": 234, "fire_incidents": 89 },
  "proposals": [...],
  "risk_score": 45,
  "ai_summary": "..."
}
```

**find_solutions:**
```json
{
  "problem_summary": "...",
  "federal_programs": [{ "name": "HUD Choice Neighborhoods", "amount": "$30M", "fit_score": 0.91 }],
  "comparable_cities": [{ "city": "Birmingham AL", "outcome": "..." }],
  "recommended_actions": [...]
}
```

---

## Streamlit — Pages finales

| Page | Source | AI? |
|---|---|---|
| 1. Overview | SQL civic_data | Non |
| 2. Real Estate | SQL properties | Non |
| 3. Businesses | SQL businesses | Non |
| 4. Comparison | SQL census | Non |
| 5. Civic Proposals | SQL Decidim (public.*) | Non |
| 6. Neighborhood Intelligence | civic_data.reports | Optionnel (regenerate) |
| 7. Velocity Map | civic_data.reports | Optionnel (regenerate) |
| 8. City Incidents | SQL city_data | Non |
| 9. Find Solutions | civic_data.reports | Oui (Grok-4-Fast) |

Pages 6, 7, 9: affichent rapport pre-calculé si existe, sinon bouton "Generate with AI"

---

## Déploiement

- Decidim: mgm.styxcore.dev (Cloudflare tunnel → localhost:3000)
- Streamlit: dashboard.styxcore.dev (Cloudflare tunnel → localhost:8501)
- MCP: stdio (Claude Desktop)

---

## Ce qui reste à coder

1. `civic_data.reports` table (SQL migration)
2. `civic_intelligence.py` (extraire logique server.py tools 7-10)
3. Adapter `server.py` pour importer + sauvegarder dans reports
4. Dashboard pages 6, 7, 9 branchées sur reports
5. Cloudflare tunnel pour Streamlit

*Last updated: 2026-03-06*
