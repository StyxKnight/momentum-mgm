# Momentum MGM — Civic Intelligence Dashboard

Streamlit dashboard prototype généré rapidement (proof of concept).
**Statut: parked** — fonctionnel dès que toutes les sources de données sont complètes.

## Ce que ça fait

7 pages connectées à notre `civic_data` PostgreSQL :

| Page | Source | Statut |
|------|--------|--------|
| Overview | Census ACS (11,334 rows) | ✅ Données réelles |
| Real Estate | Zillow via Bright Data (500 props) | ✅ Données réelles |
| Businesses | Yelp via Bright Data (500 bizs) | ✅ Données réelles |
| Neighborhood Comparison | Census multi-select | ✅ Données réelles |
| Civic Proposals | Decidim GraphQL | ⚠️ À connecter |
| Neighborhood Intelligence | Census + Zillow + Yelp | ✅ Données réelles (score à raffiner) |
| AI Query (Semantic) | civic_data.embeddings (1000 vecs) | ⚠️ RAG pipeline à brancher |

## Problèmes connus (à régler quand on revient)

### 1. Page 5 — Proposals: données fictives
La page affiche des chiffres inventés. À remplacer par un appel réel au GraphQL Decidim :
```
POST http://172.21.0.1:3000/api
Query: proposals(first: 60) { nodes { title voteCount category { name } } }
```

### 2. Page 6 — Civic Health Score: formule à raffiner
Le score composite actuel contient des seuils arbitraires. La bonne approche :
- Z-score normalisé entre tous les quartiers (pas de magic numbers)
- Poids rééquilibrés automatiquement si une composante manque
- Voir `docs/bugs.md` pour le raisonnement

### 3. Score vacance logement: bug math
`vac_rate = vac_data['value'].iloc[-1] / 100` — divise des unités par 100.
Doit être `housing_vacant / housing_total` (deux rows dans df_c).

## Pour lancer

```bash
cd momentum-mgm/dashboard
pip install -r requirements.txt
streamlit run dashboard.py
```

## Quand revenir ici

Quand ces sources seront complètes :
- [ ] Indeed Jobs (snapshot `failed` — filtre `includes` à déboguer)
- [ ] Google Maps Reviews
- [ ] Embeddings Indeed + Google Maps générés
- [ ] MCP tool 10 (`find_solutions`) validé

À ce moment, les pages 5 et 7 se branchent en ~30 min et le dashboard est complet.
