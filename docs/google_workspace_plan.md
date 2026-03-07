# Google Workspace Integration Plan — Momentum MGM
*Écrit le 2026-03-07. À lire intégralement si contexte perdu.*

---

## VISION

Le MCP server génère des analyses riches (civic_report, find_solutions, analyze_neighborhood, summarize_comments) mais ces outputs disparaissent dans le chat Claude Desktop. Aucune persistance, aucun partage possible.

**L'idée:** Brancher le MCP server sur Google Workspace pour que chaque analyse IA se retrouve automatiquement dans les outils que city hall utilise déjà — Google Sheets, Google Docs, Google Calendar. Le bridge parfait entre l'IA civique et le workflow municipal réel.

**Impact demo pour les juges:** L'admin pose une question à Claude Desktop → Claude appelle les MCP tools → les résultats apparaissent automatiquement dans un Google Doc partageable, un Google Sheet avec les données, les meetings Decidim dans Google Calendar. C'est la boucle complète visible et tangible, pas juste dans un chat éphémère.

---

## ARCHITECTURE FINALE VISÉE

```
CITIZEN                    CITY HALL (admin)              GOOGLE WORKSPACE
───────                    ─────────────────              ────────────────

Propose sur             Claude Desktop
mgm.styxcore.dev   →    + MCP Server          →    Google Docs  (rapports civic)
                         17 tools existants         Google Sheets (données quartiers)
Commente, vote     →    + 4 nouveaux tools    →    Google Calendar (meetings Decidim)
                                               →    Gmail (briefings exécutifs) [optionnel]
                              ↓
                    post_ai_response() → commentaire IA visible sur Decidim
```

---

## PRÉREQUIS — CE QUE L'UTILISATEUR DOIT FAIRE

### Étape 1 — Google Cloud Console (même projet que Gemini)

1. Aller sur https://console.cloud.google.com
2. Sélectionner le projet existant (celui qui a GOOGLE_API_KEY pour Gemini)
3. **APIs & Services → Library** — activer ces 3 APIs:
   - `Google Sheets API`
   - `Google Docs API`
   - `Google Calendar API`
   - `Gmail API` (optionnel, seulement si Google Workspace avec domaine)

### Étape 2 — Créer le Service Account

1. **IAM & Admin → Service Accounts → Create Service Account**
   - Nom: `momentum-ai`
   - Description: `Momentum MGM civic AI bridge`
   - Pas besoin d'assigner un rôle projet
2. Cliquer sur le service account créé → **Keys → Add Key → Create New Key → JSON**
3. Télécharger le fichier JSON → le placer sur le Pi à:
   `/home/styxknight/momentum-mgm/.google-service-account.json`
4. **IMPORTANT:** Ajouter `.google-service-account.json` au `.gitignore`
5. Noter l'email du service account (format: `momentum-ai@NOM-PROJET.iam.gserviceaccount.com`)

### Étape 3 — Créer et partager les ressources Google

#### Google Sheet (pour les données de quartiers)
1. Aller sur sheets.google.com → Créer un nouveau Sheet
2. Le nommer: `Momentum MGM — Civic Intelligence`
3. **Partager** avec l'email du service account → rôle **Editor**
4. Copier l'ID du Sheet depuis l'URL:
   `https://docs.google.com/spreadsheets/d/SHEET_ID_ICI/edit`
5. Garder cet ID pour le `.env`

#### Google Calendar (pour les meetings Decidim)
1. Aller sur calendar.google.com → Créer un nouveau calendrier
2. Le nommer: `Montgomery Civic — Public Meetings`
3. **Settings** du calendrier → **Share with specific people** → email service account → **Can make changes to events**
4. Dans Settings → **Integrate calendar** → copier l'**Calendar ID**
   (format: `xxxxx@group.calendar.google.com` ou email Gmail si calendrier principal)
5. Garder cet ID pour le `.env`

#### Google Docs (créés dynamiquement par le code — pas besoin de créer manuellement)
- Les Docs seront créés automatiquement dans le Drive du service account
- Pour les rendre visibles à l'admin: le code va les créer et les partager avec un email admin
- L'admin doit donc fournir son email Gmail pour recevoir les Docs

### Étape 4 — Mettre à jour le .env

Ajouter ces lignes au fichier `/home/styxknight/momentum-mgm/.env`:

```env
# Google Workspace
GOOGLE_SERVICE_ACCOUNT_JSON=/home/styxknight/momentum-mgm/.google-service-account.json
GOOGLE_SHEET_ID=COLLER_L_ID_ICI
GOOGLE_CALENDAR_ID=COLLER_L_ID_ICI
GOOGLE_ADMIN_EMAIL=EMAIL_ADMIN_ICI@gmail.com
```

---

## CE QUE LE CODE VA FAIRE — 4 NOUVEAUX TOOLS MCP

### Tool 18 — `export_to_sheet(neighborhood)`

**Ce que ça fait:**
- Appelle `get_census_trend(neighborhood)` → données Census 14 ans
- Appelle `get_city_incidents("list", neighborhood)` → comptage par source ArcGIS
- Appelle `get_business_health(neighborhood)` → santé économique Yelp
- Appelle `analyze_neighborhood(neighborhood, "all")` → scores ADI/SVI/EJI
- Crée ou met à jour un onglet dans le Google Sheet avec le nom du quartier
- Écrit toutes les données en tableau structuré avec headers
- Retourne: `{"sheet_url": "https://docs.google.com/spreadsheets/d/...", "neighborhood": "West Side", "rows_written": 47}`

**Structure du Sheet:**
```
Onglet "West Side":
| Metric            | 2012 | 2013 | ... | 2024 | Trend      |
|-------------------|------|------|-----|------|------------|
| Median Income     | $32K | $31K | ... | $28K | -2.1%/yr   |
| Poverty Rate      | 28%  | 29%  | ... | 34%  | +0.8%/yr   |
| Housing Vacancy   | 18%  | 19%  | ... | 24%  | +0.9%/yr   |
| ...               | ...  | ...  | ... | ...  | ...        |

Onglet "West Side — Incidents":
| Source              | Count  | Category      |
|---------------------|--------|---------------|
| fire_incidents      | 4,201  | public_safety |
| code_violations     | 2,847  | housing       |
| ...                 | ...    | ...           |

Onglet "Scores ADI/SVI/EJI":
| Neighborhood    | ADI Score | ADI Severity | SVI Score | ...  |
|-----------------|-----------|--------------|-----------|------|
| West Side       | 0.823     | critical      | 0.761     | ...  |
```

### Tool 19 — `create_report_doc(neighborhood)`

**Ce que ça fait:**
- Appelle `civic_report(neighborhood)` → rapport IA complet (Gemini 2.5 Flash)
- Appelle `find_solutions(problem, neighborhood)` → programmes fédéraux + best practices
- Crée un Google Doc formaté avec:
  - Titre: `Civic Intelligence Report — [Neighborhood] — [Date]`
  - Section 1: Executive Summary (2-3 paragraphes)
  - Section 2: Key Findings (liste des findings du civic_report)
  - Section 3: Data Summary (census trends, incidents, business health)
  - Section 4: Deprivation Scores (ADI/SVI/EJI avec explication)
  - Section 5: Recommended Federal Programs (de find_solutions)
  - Section 6: Comparable Cities (ce que d'autres villes ont fait)
  - Section 7: Recommended Actions (priorités concrètes)
  - Footer: `Generated by Momentum MGM Civic AI — mgm.styxcore.dev`
- Partage le Doc avec GOOGLE_ADMIN_EMAIL (Editor)
- Retourne: `{"doc_url": "https://docs.google.com/document/d/...", "title": "...", "shared_with": "admin@email.com"}`

### Tool 20 — `sync_gcal()`

**Ce que ça fait:**
- Appelle `get_meetings()` → tous les meetings Decidim (tool 16)
- Pour chaque meeting:
  - Vérifie si un event Google Calendar avec le même titre/date existe déjà (évite doublons)
  - Crée l'event avec:
    - Title: `[Momentum MGM] Meeting title`
    - Description: description du meeting + lien vers Decidim
    - Start/End time: depuis Decidim
    - Location: adresse du meeting
  - Ajoute un lien vers mgm.styxcore.dev dans la description
- Retourne: `{"synced": 6, "skipped": 0, "calendar_url": "https://calendar.google.com/..."}`

### Tool 21 — `send_briefing(neighborhood, recipient_email=None)`

**ATTENTION — Ce tool dépend de la configuration Gmail:**
- Si Google Workspace avec domaine: peut envoyer via service account + domain-wide delegation
- Si compte Gmail personnel: nécessite OAuth2 (plus complexe, moins adapté server-side)
- Si pas de config Gmail: **ce tool est optionnel, on peut le skiper**

**Ce que ça fait (si Gmail disponible):**
- Génère un résumé exécutif court (5-7 lignes) du quartier via Gemini
- Envoie un email formaté HTML à `recipient_email` (ou GOOGLE_ADMIN_EMAIL par défaut)
- Sujet: `[Momentum MGM] Civic Briefing — West Side — March 7, 2026`
- Corps: résumé + lien vers le Google Doc du rapport complet + lien Decidim
- Retourne: `{"sent": true, "to": "admin@...", "subject": "..."}`

---

## FICHIERS À CRÉER/MODIFIER

### Nouveau fichier: `mcp-server/workspace_client.py`

Module qui encapsule toute la logique Google Workspace:
```python
# Imports: google-api-python-client, google-auth
# Fonctions:
#   get_sheets_service() → Resource
#   get_docs_service() → Resource
#   get_calendar_service() → Resource
#   write_to_sheet(sheet_id, tab_name, headers, rows) → url
#   create_doc(title, sections) → url
#   create_calendar_event(cal_id, event_data) → event_id
#   list_calendar_events(cal_id) → [events]
```

### Modifier: `mcp-server/requirements.txt`

Ajouter:
```
google-api-python-client>=2.100.0
google-auth>=2.23.0
google-auth-httplib2>=0.1.1
```

### Modifier: `mcp-server/server.py`

Ajouter les 3-4 nouveaux tools après tool 17 (summarize_comments), avant `if __name__ == "__main__":`.

### Modifier: `.env`

Ajouter les 4 variables listées ci-dessus.

### Modifier: `.gitignore`

S'assurer que `.google-service-account.json` est ignoré.

---

## ORDRE D'IMPLÉMENTATION

```
1. User fournit:
   - .google-service-account.json sur le Pi
   - GOOGLE_SHEET_ID dans .env
   - GOOGLE_CALENDAR_ID dans .env
   - GOOGLE_ADMIN_EMAIL dans .env

2. Claude:
   - pip install google-api-python-client google-auth google-auth-httplib2
   - Écrire workspace_client.py
   - Écrire tool 18 export_to_sheet
   - Écrire tool 19 create_report_doc
   - Écrire tool 20 sync_gcal
   - Tester chaque tool
   - Commit + push

3. Test end-to-end:
   - export_to_sheet("West Side") → vérifier le Sheet s'est rempli
   - create_report_doc("West Side") → vérifier le Doc apparaît dans Drive
   - sync_gcal() → vérifier les 6 meetings Decidim dans Calendar
```

---

## NOTES TECHNIQUES IMPORTANTES

### Authentification service account
```python
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/calendar',
]

creds = service_account.Credentials.from_service_account_file(
    os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON'),
    scopes=SCOPES
)
```

### Partager un Doc avec l'admin
```python
# Le service account crée le doc dans SON Drive
# Pour le partager avec l'admin humain:
drive_service = build('drive', 'v3', credentials=creds)
drive_service.permissions().create(
    fileId=doc_id,
    body={'type': 'user', 'role': 'writer', 'emailAddress': ADMIN_EMAIL}
).execute()
```

### Éviter doublons Calendar
```python
# Avant de créer un event, chercher si titre+date existe déjà
existing = calendar_service.events().list(
    calendarId=cal_id,
    timeMin=start_iso,
    timeMax=end_iso,
    q=title  # recherche par texte
).execute()
if not existing.get('items'):
    # créer l'event
```

### Écriture Google Sheets
```python
# valueInputOption='USER_ENTERED' = Sheets interprète les formats (dates, nombres)
sheets_service.spreadsheets().values().update(
    spreadsheetId=SHEET_ID,
    range=f"{tab_name}!A1",
    valueInputOption='USER_ENTERED',
    body={'values': rows}
).execute()
```

---

## ÉTAT AU MOMENT DE L'ÉCRITURE (2026-03-07)

- MCP server: 17 tools fonctionnels (tools 1-17)
- Decidim: 20 citoyens, 40 proposals, 60 comments, 6 meetings seedés
- Civic loop testé: post_ai_response posté commentaires #652-656
- Google Workspace: PAS ENCORE CONFIGURÉ — en attente des credentials utilisateur
- Ce plan: à suivre dès que l'utilisateur fournit service account JSON + IDs

---

## CHECKLIST FINALE AVANT SOUMISSION (March 9)

- [ ] Google Workspace tools 18-20 codés et testés
- [ ] export_to_sheet("West Side") → Sheet visible
- [ ] create_report_doc("West Side") → Doc dans Drive
- [ ] sync_gcal() → 6 meetings dans Calendar
- [ ] Visuels Decidim (images catégories, pas de lorem ipsum)
- [ ] README à jour (21 tools)
- [ ] BRIGHT_DATA_API_KEY révoquée
- [ ] DEMO.md à jour avec le flow Google Workspace

*Last updated: 2026-03-07*
