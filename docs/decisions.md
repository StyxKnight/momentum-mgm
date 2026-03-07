# Architecture Decisions — Momentum MGM

Running log of every significant technical or design decision: what was chosen, why, and what was rejected.

---

### [DECISION-001] Embeddings — gemini-embedding-001 @ 3072d, exact search, sans index pgvector
- **Date:** 2026-03-05
- **Décision:** `gemini-embedding-001` (Google GenAI), 3072 dimensions, cosine brute force (pas d'index pgvector).
- **Rejeté:** `text-embedding-004` (retourne 404 NOT_FOUND sur API v1). IVFFlat/HNSW (incompatibles > 2000d). Tronquer à 1536d (perte de fidélité sémantique).
- **Rationale:** 3072d complet = fidélité maximale. Exact search suffisant pour < 100K embeddings (Montgomery ne dépassera pas cette échelle). Sous 200ms sur Pi à cette taille.
- **Scalabilité future:** pgvector scalar quantization ou output_dimensionality=1536 si > 500K rows.

---

### [DECISION-002] Geocoding quartiers Montgomery AL — zip codes comme proxy
- **Date:** 2026-03-05
- **Décision:** Utiliser le zip code comme identifiant de quartier pour toutes les tables civic_data.
- **Rejeté:** Nominatim reverse geocoding (résultats inconsistants pour Montgomery AL — retourne "Montgomery County" au lieu du quartier). Google Maps Geocoding API (même problème + coût).
- **Rationale:** Montgomery AL n'a pas la densité de POI nécessaire pour que les APIs de geocoding retournent des noms de quartier précis. Les zip codes sont stables, officiels, et correspondent aux délimitations Census tract. Voir `seeder/geocode_fix.py`.

---

### [DECISION-003] Seuils de sévérité civique — quartiles ADI/SVI + LISC commercial distress
- **Date:** 2026-03-07
- **Décision:** Seuils basés sur les quartiles, standard officiel ADI (UW Neighborhood Atlas) et SVI (CDC/ATSDR).

| Sévérité | Score | Signification |
|---|---|---|
| critical | > 0.75 | Top quartile — pire que 75% des quartiers de Montgomery |
| high | 0.50 – 0.75 | Au-dessus de la médiane |
| moderate | 0.25 – 0.50 | Entre 1er et 2e quartile |
| low | < 0.25 | Quartile inférieur |

- **Seuil business closure:** > 15% = détresse commerciale. Source: LISC (Local Initiatives Support Corporation).
- **Rejeté:** Seuils arbitraires (0.85/0.70/0.50) — non défendables scientifiquement.
- **Rationale:** Les quartiles sont relatifs à Montgomery elle-même. Un quartier "critical" l'est par rapport aux 71 autres tracts de la ville — pas par rapport à un chiffre inventé. Défendable devant n'importe quel décideur ou évaluateur.
- **Sources:** UW Neighborhood Atlas; CDC/ATSDR SVI 2022 Technical Documentation; LISC Commercial Corridor Distress Framework.

---

### [DECISION-004] Découplage prompts / code — templates Jinja2
- **Date:** 2026-03-07
- **Décision:** Tout prompt LLM de plus de 3 lignes vit dans `mcp-server/prompts/` comme fichier `.j2`. Le server.py charge via `jinja2.Environment(FileSystemLoader(...))`.
- **Structure:**
  ```
  mcp-server/prompts/
    base.j2           ← lorebook commun Montgomery + restrictions universelles anti-hallucination
    civic_report.j2   ← prompt analyse civique (extends base.j2)
  ```
- **Rejeté:** f-strings Python inline — mélange logique/prompt, impossible à itérer sans toucher au code.
- **Rationale:** Les prompts évoluent plus vite que le code. Découplage = versionnage indépendant, A/B testing possible, lisibilité. Pattern utilisé en production (LangChain, Semantic Kernel, PromptLayer).
- **Dépendance:** `jinja2>=3.1.0` dans `mcp-server/requirements.txt`.

---

### [DECISION-005] Hiérarchie modèles IA — Gemini primary, Grok-4 fallback ⏳ EN ATTENTE
- **Date:** 2026-03-07
- **Statut:** Noté, pas encore implémenté.
- **Décision prévue:** Gemini Flash (Google) comme modèle primaire sur tous les tools IA. Grok-4 (OpenRouter) comme fallback si Gemini échoue.
- **Rejeté (actuel):** Grok-4 primaire sur `civic_report` et `find_solutions`.
- **Rationale:** Grok-4 via OpenRouter coûte ~$0.25/appel. Gemini Flash coûte ~$0.002/appel — 125x moins cher. Pour les tests et le développement, Gemini primaire évite de brûler le budget. Grok-4 reste disponible pour les cas où la qualité d'analyse est critique.
- **Impact:** Modifier `civic_report` et `find_solutions` dans server.py pour tenter Gemini Flash d'abord, fallback Grok-4 sur exception.

---

*Last updated: 2026-03-07*
