# How It Works — Momentum MGM

Technical explanation of every layer: what it does, why it was built that way, and what judgment calls were made.

---

## The Core Problem We're Solving

Montgomery has 311 for reactive service requests ("my streetlight is broken"). What doesn't exist is the proactive layer: a structured channel where citizens propose, vote, and build civic priorities together — and where city hall can listen at scale.

Momentum MGM is that layer. It feeds context to city decision-makers in real time via AI, and it generates 311 actions automatically when proposals warrant it.

---

## Layer 1 — The Civic Platform (Decidim)

### What it is
Decidim is open-source participatory democracy software, built in Barcelona and now running in 500+ institutions: Montreal, Quebec City, Brazil's national government, Helsinki, and others. It handles proposals, voting, comments, participatory budgeting, and citizen assemblies out of the box.

### Why we chose it instead of building from scratch
- **Credibility signal.** Judges see "Decidim" and know it's not a toy. It runs at 40,000-participant scale.
- **Feature completeness.** Proposals, voting, user accounts, moderation, admin dashboard — all built. A custom FastAPI would take weeks to reach parity.
- **ARM64 constraint.** The official Decidim Docker image is amd64-only. We installed natively on Ruby 3.3.10 on a Raspberry Pi 5 — which is actually a proof of how lightweight the deployment can be.

### The 10 categories — why these specifically
```
infrastructure   → Roads, bridges, sidewalks, lighting
environment      → Water, sewers, flooding, air quality
housing          → Blight, abandoned buildings, affordable housing
public_safety    → Crime prevention, police, fire, emergency
transportation   → Transit, bike lanes, parking, accessibility
health           → Public health, mental health, homelessness
education        → Schools, youth programs, libraries
economy          → Small business, jobs, investment
parks_culture    → Parks, arts, sports, community spaces
governance       → Transparency, budget participation, civic processes
```

These are not arbitrary. They are:
1. **The same taxonomy used in 311 systems worldwide** — compatibility with Montgomery's existing infrastructure
2. **Directly mappable to city departments** — Infrastructure = Public Works, Public Safety = MPD, etc.
3. **Aligned with Mayor Reed's stated 2026 priorities** without hardcoding any single priority as "most important" — the platform surfaces what *citizens* prioritize, not what we assume

Each category is a separate Decidim Participatory Process with its own Proposals component. This gives each category a dedicated space, its own stats, and its own admin view.

### Navigation note
In Decidim, proposals live inside Participatory Processes → Components. The path is:
`Home → Processes → [Category Name] → Proposals`

This is 3 clicks deep — a known Decidim UX pattern. For the demo, navigate directly to a process URL. For production, the homepage can be configured to surface top proposals directly.

---

## Layer 2 — The Data Pipeline (Bright Data + AI)

### The problem with an empty platform
An empty civic platform kills demos and kills trust. Citizens don't submit proposals into a void. We needed real Montgomery civic content from day 1.

### Step 1 — scrape.py (Bright Data)

**What it does:**
Collects real civic intelligence from Montgomery public sources using Bright Data's web intelligence platform.

**Why Bright Data and not plain requests:**
Montgomery's open data portal (`opendata.montgomeryal.gov`) returns 403 on direct programmatic access — it blocks crawlers. Bright Data's Web Unlocker rotates proxies, handles CAPTCHAs, and renders JavaScript. It's the only way to reliably access these sources at scale.

**What we scrape:**
```
city_pages.json       → Mayor Reed news, 311 portal, open data hub, city budget, State of the City 2026
category_searches.json → 10 Google searches (one per civic category) via Bright Data SERP API
mayor_priorities.json → Mayor Reed's stated priorities from press coverage and official statements
311_data.json         → Montgomery 311 service categories and open request data
```

**The judgment:** We scrape for *context*, not for content. The AI generates the proposals — but grounded in real Montgomery data: real street names, real neighborhoods (Capitol Heights, Old Cloverdale, West Montgomery, Southlawn, Dexter Avenue), real issues cited in press coverage.

**Bright Data usage:** ~25 requests per full scrape run. Budget: 4,666 requests available. The scraper can run daily for months without exhausting the quota.

### Step 2 — seed.py (AI Generation + Rails Insertion)

**What it does:**
1. Loads the scraped JSON context
2. Calls an AI model to generate 6 realistic proposals per category (60 total)
3. Inserts them into Decidim via Rails ActiveRecord (not GraphQL — see below)

**AI model choice:**
- **Primary:** OpenRouter → `x-ai/grok-4-fast` — fast, cost-effective, strong instruction following
- **Fallback:** Google Gemini 2.5 Flash direct — activates automatically if OpenRouter fails

**Why not GraphQL for insertion:**
Decidim 0.31's GraphQL API is read-only by default. The mutation type exposes 0 fields on introspection. Admin writes must go through Rails ActiveRecord directly. Our solution: Python generates proposals JSON → writes to `/tmp/` → Rails runner script reads it and inserts via ActiveRecord. Clean separation: Python owns AI logic, Rails owns data integrity.

**The quality bar for proposals:**
The AI prompt specifically asks for:
- First-person plural voice ("We propose...", "Our neighborhood needs...")
- Specific Montgomery references (real streets, neighborhoods, landmarks)
- Actionable, concrete civic concerns
- 150-300 words — substantial enough to feel real

**Result:** Proposals like "Repair Potholes on Zelda Road in Capitol Heights" and "Support Minority-Owned Businesses on Dexter Avenue" — not generic filler.

---

## Layer 3 — The MCP Server (Claude ↔ Decidim)

### What MCP is
Model Context Protocol is Anthropic's open standard for connecting AI models to external systems. When a city administrator opens Claude Desktop and asks a question, Claude calls our MCP tools to get real data before answering.

### Why this is genuinely new
No existing civic platform has an AI admin bridge. Barcelona's Decidim doesn't. Montreal's doesn't. Brazil's doesn't. The MCP server is what makes Momentum MGM a different category of product, not just another Decidim deployment.

### Tools exposed to Claude

| Tool | What it does | Judgment used |
|---|---|---|
| `get_proposals(category?, limit?)` | Fetch proposals from Decidim GraphQL | Filter by category — lets admin drill into specific civic areas |
| `classify_proposal(text)` | AI classification via Gemini Flash | Returns category, summary, confidence, 311 actionability — bridges citizen language to civic taxonomy |
| `analyze_trends()` | Count + rank proposals by votes | Surfaces what citizens care about most — the signal city hall needs |
| `recommend_action(topic)` | AI advisory for city administration | Returns department to involve, urgency, concrete next steps, whether to open a 311 ticket |
| `get_platform_summary()` | Full platform state snapshot | Quick briefing for a mayor who has 2 minutes |

### The classification judgment
When classifying a proposal, the AI returns:
- `category` — one of the 10 civic categories
- `summary` — one neutral sentence
- `confidence` — 0.0 to 1.0
- `keywords` — top 3 civic keywords
- `311_actionable` — boolean: does this warrant a 311 service request?
- `311_note` — if actionable, what type of request

This is the bridge between the proactive platform (Momentum) and the reactive system (311). A citizen submits "Fix the sidewalk on Dexter Avenue" → AI classifies as infrastructure, 311_actionable: true, 311 service type: "Sidewalk Repair Request". The city sees both the community voice and the operational action item.

### How Claude Desktop connects
The MCP server runs as a stdio process. Claude Desktop loads it via `~/.claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "momentum-mgm": {
      "command": "python3",
      "args": ["/path/to/mcp-server/server.py"],
      "env": { "DECIDIM_URL": "https://mgm.styxcore.dev", ... }
    }
  }
}
```
From that point, any Claude conversation can call civic data tools transparently.

---

## Key Technical Decisions Summary

| Decision | Why |
|---|---|
| Decidim over custom build | Proven at scale, credibility signal, 5-day timeline |
| Native install over Docker | Official Docker image is amd64-only, Pi is ARM64 |
| 10 categories (not Reed's 5 priorities) | Civic taxonomy is stable; priorities change with each mayor |
| Rails runner over GraphQL for writes | Decidim 0.31 GraphQL is read-only — no choice |
| OpenRouter over direct Google/Anthropic | One key, multiple models, pay-per-use, easy fallback |
| Bright Data over plain requests | Montgomery open data returns 403 on direct access |
| Venv per component (seeder, mcp-server) | Isolation — no system Python conflicts on the Pi |
| Proposals nested in Processes (not Assembly) | Processes = time-bound civic consultations — correct Decidim model for category-based participation |

---

*Last updated: 2026-03-05*
