# Prompt Engineering — Momentum MGM
*Standard de référence pour tous les prompts AI du projet*

---

## 1. Paramètres d'inférence LLM

Ces paramètres contrôlent le comportement du modèle au niveau de la génération de tokens.
Ils se définissent dans l'appel API, pas dans le prompt.

### Temperature
Contrôle la créativité vs la précision. Plus c'est bas, plus le modèle choisit le token le plus probable.

| Use case | Valeur recommandée |
|---|---|
| Analyse de données structurées (notre cas) | 0.1 — 0.2 |
| Recherche de solutions / recommandations | 0.3 — 0.5 |
| Génération créative | 0.7 — 1.0 |

**Règle Momentum:** analyse = 0.1, find_solutions = 0.4

### Top-P (Nucleus Sampling)
Limite le pool de tokens considérés à ceux dont la probabilité cumulée atteint P.
Ne pas utiliser en même temps que Top-K — choisir l'un ou l'autre.

- Analyse factuelle: 0.85 — 0.90
- Génération libre: 0.95

### Top-K
Limite le pool aux K tokens les plus probables. Moins utilisé sur les APIs commerciales.
Laisser au défaut sauf cas spécifique.

### Frequency Penalty
Pénalise les tokens qui réapparaissent souvent dans la sortie (réduit les répétitions).
- Valeur utile: 0.1 — 0.3 pour les rapports structurés

### Presence Penalty
Pénalise tout token déjà apparu, qu'il soit fréquent ou non (pousse la diversité).
Ne pas utiliser avec frequency_penalty en même temps.

### Max Tokens
Toujours définir explicitement. Évite les sorties tronquées ou les coûts surprises.

| Tool | Max tokens recommandé |
|---|---|
| Analyse quartier | 600 |
| Find solutions | 900 |
| Réponse courte | 300 |

### Min-P (2025+)
Paramètre émergent, meilleur que Top-P pour les modèles open-source.
Pour APIs commerciales (OpenRouter/Grok): utiliser Top-P.

---

## 2. Architecture du System Prompt

Structure complète dans l'ordre d'injection. Chaque section a un rôle précis.

```
[ROLE]
[LEVEL OF ROLE]
[CONTEXT / LOREBOOK]
[RAG — données injectées dynamiquement]
[CHAIN OF THOUGHT]
[FEW-SHOT EXAMPLES]
[RESTRICTIONS]
[OUTPUT SCHEMA]
```

---

### 2.1 ROLE
Définit l'identité du modèle. Doit être précis, professionnel, ancré dans le domaine.

Mauvais: "You are a helpful AI assistant."
Bon: "You are a senior civic data analyst embedded in the City of Montgomery, Alabama's planning department."

Le rôle doit correspondre exactement à la tâche. Un rôle trop générique = réponses génériques.

---

### 2.2 LEVEL OF ROLE
Définit le niveau d'expertise et le registre de communication.
Sert à calibrer la précision du langage, la tolérance à l'ambiguïté, et le niveau de détail.

Exemple: "Expert level. You speak with the precision of a data scientist and the pragmatism of a city planner. You never speculate. You never add context from outside the data provided."

---

### 2.3 CONTEXT — Lorebook
Faits stables sur Montgomery qui ne changent pas entre les appels.
Cette section est statique — elle ne dépend pas de la requête.
C'est l'équivalent d'un lorebook: le modèle "connaît" ce contexte avant de voir les données.

Contenu pour Momentum MGM:
- Montgomery AL: ~200,000 résidents, comté de Montgomery (FIPS 01101)
- 71 census tracts ACS, données 2012-2024
- Quartiers mappés par zip code (DECISION-002 — OSM/Google Maps insuffisants pour Montgomery)
- Sources de données disponibles: Census ACS, ArcGIS open data, Yelp, Zillow
- Catégories civiques: infrastructure, environment, housing, public_safety, transportation, health, education, economy, parks_culture, governance

---

### 2.4 RAG — Injection dynamique
Les données réelles retournées par les tools SQL, injectées dans le prompt au moment de l'appel.
C'est la seule source de vérité autorisée pour l'analyse.

Règles d'injection:
- Données brutes uniquement, jamais pré-interprétées
- Format JSON compact — pas de prose dans les données
- Section clairement délimitée (DATA START / DATA END ou balises XML)
- Si une source est vide, ne pas l'inclure plutôt que d'injecter null partout

Exemple de structure:
```
<DATA>
{
  "neighborhood": "West Side",
  "census_trend": { ... },
  "city_incidents": { ... },
  "businesses": { ... }
}
</DATA>
```

---

### 2.5 CHAIN OF THOUGHT
Instructions de raisonnement étape par étape.
Prouvé empiriquement: améliore la précision de 18% à 78% sur tâches complexes (Google, 2022).
Doit être adapté à la tâche — pas générique.

Pour l'analyse civique Momentum:
1. Lire chaque métrique Census et noter sa direction (slope > 0 = amélioration)
2. Filtrer les métriques peu fiables (R² < 0.5 = signal trop bruité pour conclure)
3. Lire les conditions actuelles (incidents, violations, logement)
4. Relier les métriques entre elles (ex: revenu décline + violations élevées = spirale)
5. Formuler 3 à 5 constats factuels maximum, chacun ancré dans un chiffre de la DATA section

---

### 2.6 FEW-SHOT EXAMPLES
Montrer 1 à 3 exemples entrée/sortie au format exact attendu.
C'est la technique la plus impactante selon la recherche 2025.
Les exemples doivent être réels ou très proches du réel — pas inventés.

Pour Momentum: utiliser West Side comme exemple canonique une fois les données validées.

---

### 2.7 RESTRICTIONS
Le cadenas anti-hallucination. Doit être explicite, court, non ambigu.

Restrictions obligatoires pour tous les prompts Momentum:
- "Only reference numbers explicitly present in the DATA section above."
- "Never add statistics, percentages, or comparisons from your training data."
- "If a metric is absent from the data, omit it entirely. Never estimate or infer."
- "Do not use hedging language ('might', 'could', 'possibly') — only what the data shows."

---

### 2.8 OUTPUT SCHEMA
Forcer un format JSON défini.
Prouvé pour réduire les hallucinations: le modèle met null plutôt qu'inventer si le champ n'a pas de valeur dans les données.
Le schema doit être minimal — uniquement les champs nécessaires.

---

## 3. Flow Momentum — 3 étapes

### Étape 1: RESEARCH (pas d'IA)
Tools SQL qui retournent des données brutes. Aucune IA impliquée.
- `get_census_trend(neighborhood)` → Census ACS 2012-2024, régression linéaire
- `get_city_incidents(neighborhood, source)` → ArcGIS open data, count brut
- `get_business_health(neighborhood)` → Yelp, health score brut

### Étape 2: ANALYSIS (Grok-4, temperature=0.1)
Un seul tool qui prend toutes les données de l'étape 1 et produit une analyse factuelle cadenassée.
- `analyze_neighborhood(neighborhood)` → appelle les 3 tools research, injecte dans prompt, retourne JSON structuré
- Le prompt utilise la structure complète: Role + Level + Lorebook + RAG + CoT + Restrictions + Schema

### Étape 3: RESOLUTION (Grok-4, temperature=0.4)
Prend les constats confirmés de l'étape 2 et cherche des solutions réelles.
- `find_solutions(problem, neighborhood)` → programmes fédéraux HUD/CDBG/EPA/DOT + villes comparables
- Temperature plus haute ici car on veut de la créativité dans les solutions, pas seulement des faits
- Restrictions allégées: peut référencer des programmes connus, mais doit citer les sources

---

## 4. Règles absolues Momentum

Ces règles ne se négocient pas, quel que soit le tool:

1. Temperature data analysis = 0.1 maximum
2. Structured JSON output obligatoire sur tous les tools AI
3. Section RAG toujours délimitée par balises — jamais de données flottantes dans le prompt
4. Restrictions anti-hallucination toujours présentes, jamais omises pour "gagner des tokens"
5. Max tokens défini explicitement à chaque appel
6. Pas de frequency_penalty ET presence_penalty ensemble — choisir un seul

---

---

## 5. Templates Jinja2 — Découplage prompt / code

### Pourquoi Jinja2 et pas des f-strings dans le code

Dans un système de production, les prompts ne vivent pas dans le code Python. Ils vivent dans des fichiers templates versionnés séparément. Raisons concrètes:

Modifier un prompt ne doit pas nécessiter de toucher à la logique du tool. Les prompts évoluent vite (itérations, tests A/B, corrections de comportement) — mélanger ça avec le code Python crée de la dette technique inutile. Jinja2 permet la logique conditionnelle, les boucles, et l'héritage de templates directement dans le fichier prompt, sans Python.

### Structure de fichiers

```
mcp-server/
  prompts/
    base.j2                  ← lorebook commun (Montgomery context)
    analyze_neighborhood.j2  ← tool analyze_neighborhood
    find_solutions.j2        ← tool find_solutions
  server.py                  ← tools: chargent et rendent les templates
```

### Syntaxe Jinja2 utilisée dans ce projet

```jinja2
{# Commentaire #}
{{ variable }}               {# Injection de valeur #}
{{ data.census.median_income | round(0) }}  {# Filtre #}
{% if data.census %}...{% endif %}          {# Conditionnel — omet si absent #}
{% for k, v in data.items() %}...{% endfor %}  {# Boucle #}
{% extends "base.j2" %}      {# Héritage du lorebook commun #}
{% block content %}...{% endblock %}
```

### Chargement au runtime dans server.py

```python
from jinja2 import Environment, FileSystemLoader

_jinja = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "prompts"),
    trim_blocks=True,
    lstrip_blocks=True,
)

def _render(template_name: str, **kwargs) -> str:
    return _jinja.get_template(template_name).render(**kwargs)
```

### Règle

Tout prompt de plus de 3 lignes va dans un fichier `.j2`. Les f-strings inline sont interdits pour les prompts LLM dans ce projet.

---

*Dernière mise à jour: 2026-03-07*
*Sources: Lakera Prompt Engineering Guide 2026, Google Prompting Strategies, MIT Sloan AI Essentials, Urban Institute NCDB methodology, OpenAI Best Practices, PromptLayer Jinja2 Guide, Microsoft Semantic Kernel Jinja2 docs*
