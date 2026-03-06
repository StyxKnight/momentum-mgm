# Bugs & Solutions

Running log of every significant issue encountered during the hackathon: root cause, fix, and lessons learned.

---

## Template

```
### [BUG-XXX] Short description
- **Date:** YYYY-MM-DD
- **Severity:** Critical / High / Medium / Low
- **Status:** Open / Fixed / Won't Fix
- **Symptom:** What we observed
- **Root Cause:** Why it happened
- **Fix:** What we changed
- **Lesson:** What to remember
```

---

## Active Issues

- **iptables rule not persistent** — port 3000 rule lost on reboot. Needs `/etc/iptables/rules.v4` entry.
### [BUG-005] config.hosts inside conditional block — never executed
- **Date:** 2026-03-05
- **Severity:** High
- **Status:** Fixed
- **Symptom:** `ActionDispatch::HostAuthorization` blocks `mgm.styxcore.dev` even after adding config.hosts
- **Root Cause:** The `config.hosts` lines were placed inside `if ENV["RAILS_BOOST_PERFORMANCE"]` block. Since that env var isn't set, they never ran.
- **Fix:** Move `config.hosts` lines outside the conditional, directly in the `Rails.application.configure` block.
- **Lesson:** Always verify indentation/scope when editing Rails environment configs.

### [BUG-006] Decidim Organization host mismatch
- **Date:** 2026-03-05
- **Severity:** High
- **Status:** Fixed
- **Symptom:** Decidim returns 403/exception — organization lookup fails for `mgm.styxcore.dev`
- **Root Cause:** Decidim seeds the Organization with `host: localhost`. When accessed via public domain, the lookup fails.
- **Fix:** `UPDATE decidim_organizations SET host = 'mgm.styxcore.dev' WHERE host = 'localhost';`
- **Lesson:** After any domain change, update the Organization host in DB.

### [BUG-007] Docker containers cannot reach host ports (iptables)
- **Date:** 2026-03-05
- **Severity:** Medium
- **Status:** Fixed
- **Symptom:** Nginx container times out trying to reach `172.21.0.1:3000` (Decidim on host)
- **Root Cause:** Default Docker iptables rules block container → host connections on non-standard ports.
- **Fix:** `sudo iptables -I INPUT -s 172.21.0.0/16 -p tcp --dport 3000 -j ACCEPT`
- **Lesson:** iptables rule is not persistent across reboots. Add to `/etc/iptables/rules.v4` or a startup script.



---

## Resolved Issues

### [BUG-001] Shakapacker manifest missing on first boot
- **Date:** 2026-03-05
- **Severity:** High
- **Status:** Fixed
- **Symptom:** Decidim server returns 500 on all routes — `Shakapacker::Manifest::MissingEntryError`
- **Root Cause:** webpack/shakapacker assets were never compiled. Rails expects a compiled `manifest.json` in `public/decidim-packs/` before it can serve any page.
- **Fix:** Run `bundle exec bin/shakapacker` once after install to compile all frontend assets (~40 sec on Pi ARM64).
- **Lesson:** Always compile assets before first boot. In production use `RAILS_ENV=production bundle exec bin/shakapacker` and serve from CDN or Nginx static files.

### [BUG-002] rbenv install fails silently in background shell
- **Date:** 2026-03-05
- **Severity:** High
- **Status:** Fixed
- **Symptom:** `rbenv install 3.3.6` run via `nohup ... &` — process starts but Ruby never appears in `~/.rbenv/versions/`
- **Root Cause:** Background shell did not inherit the correct PATH and rbenv init environment. The install process exited silently without writing to the version directory.
- **Fix:** Run `rbenv install` in a foreground shell with `export PATH="$HOME/.rbenv/bin:$PATH" && eval "$(rbenv init -)"` explicitly set first.
- **Lesson:** Never background rbenv/ruby install. Run foreground. Takes ~20 min on ARM64 but is reliable.

### [BUG-003] PostgreSQL not accessible from host (no port binding)
- **Date:** 2026-03-05
- **Severity:** Medium
- **Status:** Fixed (non-issue)
- **Symptom:** `rails db:migrate` fails — cannot connect to `localhost:5432`
- **Root Cause:** Assumed Docker PostgreSQL was the only instance. A native PostgreSQL 15 was already running on `127.0.0.1:5432` on the Pi.
- **Fix:** Use `127.0.0.1:5432` (not `::1`). Native PostgreSQL is the correct target — create `momentum` database there via `sudo -u postgres psql`.
- **Lesson:** Check `ss -tlnp | grep 5432` before assuming PostgreSQL config.

### [BUG-004] Decidim generated app targets wrong Ruby version
- **Date:** 2026-03-05
- **Severity:** Low
- **Status:** Fixed
- **Symptom:** `rbenv: version '3.3.4' is not installed` when running any rails command inside momentum-app
- **Root Cause:** `decidim` generator writes `.ruby-version` with the version it was built against (3.3.4), not the installed version (3.3.10).
- **Fix:** `echo "3.3.10" > .ruby-version`
- **Lesson:** Always check `.ruby-version` after `decidim` app generation.

---

### [BUG-008] Sidekiq fails — not in Gemfile
- **Date:** 2026-03-05
- **Severity:** Medium
- **Status:** Fixed
- **Symptom:** `decidim-sidekiq.service` crashes — `bundler: command not found: sidekiq`
- **Root Cause:** Decidim depends on Sidekiq but doesn't add it to the generated Gemfile automatically.
- **Fix:** Add `gem "sidekiq", "~> 7.0"` to Gemfile + `bundle install`
- **Lesson:** Always check Gemfile after `decidim` generation for missing runtime deps.

### [BUG-009] Sidekiq can't connect to Redis — port not exposed
- **Date:** 2026-03-05
- **Severity:** Medium
- **Status:** Fixed
- **Symptom:** `Connection refused - connect(2) for 127.0.0.1:6379`
- **Root Cause:** Redis runs in Docker with no port binding to host. Native processes can't reach it.
- **Fix:** Add `ports: - "127.0.0.1:6379:6379"` to redis service in rpg-forum docker-compose.yml
- **Lesson:** Any native service (non-Docker) that needs Redis must have the port exposed. Same pattern as PostgreSQL.

### [BUG-010] rbenv not initialized in systemd service context
- **Date:** 2026-03-05
- **Severity:** High
- **Status:** Fixed
- **Symptom:** systemd service fails with exit code 127 — `bundle` not found
- **Root Cause:** systemd runs with minimal environment. `rbenv init` must be called explicitly.
- **Fix:** Wrapper script `/usr/local/bin/decidim-start.sh` that exports HOME, adds rbenv to PATH, calls `eval "$(rbenv init -)"`, then execs bundle.
- **Lesson:** Never set rbenv shim paths directly in systemd Environment= — use a wrapper script.

---

### [BUG-011] Decidim GraphQL API exposes 0 mutations
- **Date:** 2026-03-05
- **Severity:** High
- **Status:** Fixed
- **Symptom:** `__schema { mutationType { fields } }` returns empty array. `createProposal` mutation unavailable.
- **Root Cause:** Decidim 0.31 GraphQL API is read-only by default. Admin mutations are not exposed without additional configuration (decidim-api gem settings or API tokens).
- **Fix:** Bypass GraphQL entirely for seeding. Use Rails runner (`/usr/local/bin/decidim-start.sh rails runner script.rb`) to insert records directly via ActiveRecord. seed.py generates proposals JSON → Rails script inserts them.
- **Lesson:** Decidim GraphQL = good for reads, not for admin writes. Use Rails runner or direct DB for seeding.

### [BUG-012] Decidim seed data corrupts search index — callbacks fail on save
- **Date:** 2026-03-05
- **Severity:** Medium
- **Status:** Fixed
- **Symptom:** `rails runner` script fails with `undefined method '[]' for nil` inside `decidim/searchable.rb` when trying to save admin user.
- **Root Cause:** Fake seed data (from `rails db:seed`) creates records with malformed searchable content. Saving any user triggers a reindex callback that iterates over related records and chokes on nil content.
- **Fix:** Use `update_columns(...)` instead of `save!` to bypass all callbacks and validations when updating admin credentials.
- **Lesson:** `update_columns` = direct SQL UPDATE, no callbacks, no validations. Use it when touching seed-polluted records.

### [BUG-015] Google AI Studio free tier quota = 0, billing not enabled
- **Date:** 2026-03-05
- **Severity:** High
- **Status:** Fixed
- **Symptom:** `429 RESOURCE_EXHAUSTED — quota exceeded, limit: 0` on every Gemini call
- **Root Cause:** Free tier API key from AI Studio has `limit: 0` when billing is not activated on the associated Google Cloud project.
- **Fix:** Switched AI provider for seeder to OpenRouter (already configured, $7 balance, Grok functional). The MCP server classifier keeps using OpenRouter too for consistency.
- **Lesson:** Google AI Studio free keys require billing enabled on the GCP project. Alternative: use OpenRouter as a unified AI gateway — one key, multiple models, pay-per-use.

### [BUG-013] google-generativeai SDK deprecated — model not found
- **Date:** 2026-03-05
- **Severity:** High
- **Status:** Fixed
- **Symptom:** `404 models/gemini-1.5-flash is not found for API version v1beta`
- **Root Cause:** `google-generativeai` package is fully deprecated as of early 2026. It targets the old v1beta API where `gemini-1.5-flash` no longer resolves.
- **Fix:** Migrate to `google-genai` package. New import: `from google import genai`. New model name: `gemini-2.0-flash`.
- **Lesson:** Always use `google-genai` (new SDK), never `google-generativeai` (deprecated). Model ID: `gemini-2.0-flash`.

### [BUG-014] Rails runner `save!` fails — `Password is too short`
- **Date:** 2026-03-05
- **Severity:** Low
- **Status:** Fixed
- **Symptom:** ActiveRecord::RecordInvalid on admin password update — password too short.
- **Root Cause:** Decidim enforces a minimum password length (12 chars by default). `Momentum2026!` is 13 chars — was actually fine. Real issue was the search index callback (see BUG-012).
- **Fix:** Use `update_columns` with `Devise::Encryptor.digest` to bypass validations entirely.
- **Lesson:** When you need to set a password without Devise validations, use `update_columns(encrypted_password: Devise::Encryptor.digest(Model, "password"))`.

---

### [BUG-016] Decidim API 302 redirect when queried via localhost
- **Date:** 2026-03-05
- **Severity:** High
- **Status:** Fixed
- **Symptom:** POST to `http://localhost:3000/api` returns 302 redirect to `/system/`
- **Root Cause:** Decidim looks up the Organization by the request host. `localhost` doesn't match the org host (`mgm.styxcore.dev`), so it redirects to system setup.
- **Fix:** Always query the API via the public URL: `https://mgm.styxcore.dev/api`. Update `DECIDIM_URL` in `.env` accordingly.
- **Lesson:** Never use localhost for Decidim API calls when org host is a public domain.

### [BUG-017] Decidim Organization created with fake multilingual seed data
- **Date:** 2026-03-05
- **Severity:** Medium
- **Status:** Fixed
- **Symptom:** `org.name` returns a hash with 40+ locales of fake company names ("Flatley and Sons", etc.)
- **Root Cause:** `rails db:seed` populates the org with Faker data across all supported locales.
- **Fix:** `org.update_columns(name: {"en" => "Momentum MGM"}, ...)` — direct SQL, bypasses reindex callback that crashes on nil seed data.
- **Lesson:** After `rails db:seed`, always reset org name/host before doing anything else. Use `update_columns` not `save!`.

### [BUG-018] `Decidim::Coauthorship` model — wrong attribute names
- **Date:** 2026-03-05
- **Severity:** Medium
- **Status:** Fixed
- **Symptom:** `proposal.coauthorships.build(author: admin, organization: org)` raises `UnknownAttributeError`
- **Root Cause:** `Decidim::Coauthorship` uses raw FK columns, not ActiveRecord associations in the build call. Actual columns: `decidim_author_id`, `decidim_author_type`. No `organization` column.
- **Fix:** `proposal.coauthorships.build(decidim_author_id: admin.id, decidim_author_type: admin.class.name)`
- **Lesson:** Always introspect with `Model.column_names` before assuming attribute names in Decidim models.

### [BUG-019] Rails runner script in heredoc — `save!` backslash escape issue
- **Date:** 2026-03-05
- **Severity:** Low
- **Status:** Fixed
- **Symptom:** `rails runner` fails with `syntax error, unexpected backslash` on `save!` or `update!`
- **Root Cause:** When passing Ruby code inline via shell (single-quoted heredoc or string), the `!` in method names like `save!` gets interpreted by the shell in some contexts.
- **Fix:** Write Ruby scripts to a `.rb` file first (`/tmp/script.rb`), then call `rails runner /tmp/script.rb`. Never pass complex Ruby inline via shell string.
- **Lesson:** Always use file-based Rails runner for anything beyond a one-liner.

### [BUG-020] google-genai free tier limit = 0 on new AI Studio key
- **Date:** 2026-03-05
- **Severity:** Medium
- **Status:** Worked around
- **Symptom:** `429 RESOURCE_EXHAUSTED — limit: 0` immediately on first API call
- **Root Cause:** Google AI Studio free keys have `limit: 0` when the associated GCP project doesn't have billing enabled. The key exists but the quota is zero.
- **Fix:** Use OpenRouter as primary AI provider (already configured). Gemini kept as fallback for when billing is eventually enabled.
- **Lesson:** Google AI Studio free keys require billing activated on GCP project. OpenRouter is a better default for hackathon use — one key, multiple models, pay-per-use.

---

---

## Architecture Divergences — Plan vs Reality

Recorded during Day 2 full doc audit. These are intentional deviations from original design, not bugs. Kept here for hackathon transparency.

### [DIV-001] Seeder insertion method: GraphQL → Rails runner
- **Date:** 2026-03-05
- **Original plan:** seed.py inserts proposals via Decidim GraphQL API (`createProposal` mutation)
- **Reality:** Decidim 0.31 GraphQL exposes 0 mutations (public read-only). Rails runner via `decidim-start.sh rails runner script.rb` is the only write path.
- **Impact:** seed.py calls `insert_proposals_via_rails()` instead of any GraphQL mutation. backend.md and architecture.md updated.

### [DIV-002] Primary AI provider: Gemini Flash → Grok-4-Fast via OpenRouter
- **Date:** 2026-03-05
- **Original plan:** Gemini Flash (google-genai SDK) as primary AI for seeder + MCP classifier
- **Reality:** Google AI Studio free tier has `limit: 0` quota. Switched to OpenRouter (`x-ai/grok-4-fast`) as primary. Gemini kept as fallback only.
- **Impact:** All AI calls go through OpenRouter first. Gemini is `except` branch. pitch-deck.md, architecture.md, README.md updated.

### [DIV-003] MCP server transport: HTTP port → stdio
- **Date:** 2026-03-05
- **Original plan:** MCP server exposed on HTTP port (e.g. 8080) for Claude Desktop to connect
- **Reality:** FastMCP uses stdio transport by default. Claude Desktop runs it as a subprocess (`command` + `args` in config), not via HTTP. No port opened.
- **Impact:** architecture.md updated. No network config needed for MCP.

### [DIV-004] MCP server file structure: tools/ subdirectory → flat
- **Date:** 2026-03-05
- **Original plan:** `mcp-server/tools/proposals.py`, `classifier.py`, `clusters.py`, `context.py`
- **Reality:** All 6 tools are in a single `server.py`. `decidim_client.py` is the only other file.
- **Impact:** backend.md directory structure updated.

### [DIV-005] MCP tools: planned set → actual set
- **Date:** 2026-03-05
- **Original plan:** `get_clusters`, `create_proposal` tools existed
- **Reality:** These tools do not exist. Actual 6 tools: `get_proposals`, `classify_proposal`, `analyze_trends`, `recommend_action`, `get_platform_summary`, `get_montgomery_context`
- **Impact:** backend.md tool list rewritten. README.md and architecture.md updated.

### [DIV-006] Civic taxonomy: 5 Reed priorities → 10 civic categories
- **Date:** 2026-03-05
- **Original plan:** AI classifier aligned to Reed's 5 named priorities (public_safety, blight, economy, infrastructure, services)
- **Reality:** Using 10 civic categories that map to 311 and city departments. Reed priorities change with mayors; civic taxonomy is stable. No `reed_priority` field in category data.
- **Impact:** classify_proposal prompt, CATEGORIES dict, seeder categories all use the 10-category taxonomy.

### [DIV-007] civic_data DB table → JSON files only
- **Date:** 2026-03-05
- **Original plan:** Scraped Montgomery data stored in a `civic_data` PostgreSQL table
- **Reality:** Scraped data lives as 4 JSON files in `seeder/data/scraped/`. MCP reads them directly. No extra DB schema needed.
- **Impact:** No migration needed. Simpler. `get_montgomery_context` reads files directly.

### [DIV-008] Sidekiq auto-classification → on-demand only
- **Date:** 2026-03-05
- **Original plan:** When a citizen submits a proposal, a Sidekiq job auto-classifies it and writes the category back to the record
- **Reality:** Not implemented. Classification is on-demand via `classify_proposal` MCP tool only. AI metadata (category, summary) not stored back into Decidim.
- **Impact:** Still an open item for Day 4+ if time allows.

---

## Recurring Patterns to Watch

### [PATTERN-002] Invented census tract numbers
- **First occurrence:** 2026-03-05 (Day 3 lake.py build)
- **Pattern:** AI invents plausible-looking census tract numbers (0101.00, 0102.00...) that don't match reality. Montgomery County AL has 71 real tracts numbered 1–61 with subdivisions (22.01, 22.02, 29.01, etc.), confirmed via Census API (state=01, county=101).
- **Fix:** Never hardcode census tract → neighborhood mappings. Populate dynamically: tract IDs from Census API responses, neighborhood names from Nominatim reverse geocoding (lat/lon → suburb).
- **Search for:** any hardcoded INSERT with census tract numbers in SQL files.

### [PATTERN-001] "Mayor Reed priorities" creep
- **First occurrence:** 2026-03-05 (Day 3 planning session)
- **Pattern:** AI assistants (Claude included) tend to re-introduce "Mayor Reed's 5 priorities" or "Reed Priority #1/#2" into code, docs, and tool descriptions — even after being explicitly corrected.
- **Why it happens:** Training data likely contains many Decidim/civic platform examples that reference mayor priorities. The association is strong.
- **Correct behavior:** Always use the 10 civic categories. No mayor names in taxonomy. Categories map to city departments and 311, not to any individual politician.
- **Search for:** `reed priority`, `reed_priority`, `Reed's 5`, `Priority #`, `mayor reed priority` — any of these in code or docs is wrong.
- **Exception:** `mayor_priorities.json` scraped data file and `how_it_works.md`/`bugs.md` explanations are correct — they reference Reed historically to explain WHY we chose 10 categories instead.

---

### [BUG-023] PostgreSQL: comparaison UUID vs TEXT — "operator does not exist"
- **Date:** 2026-03-05
- **Severity:** Medium
- **Status:** Fixed
- **Symptom:** `psycopg2.errors.UndefinedFunction: operator does not exist: uuid = text` dans une requête SQL qui comparait `p.id` (UUID) avec `e.source_id` (aussi UUID, mais mal assumé comme TEXT dans le code).
- **Root Cause:** PostgreSQL est **strictement typé** — il ne convertit jamais implicitement entre types, même entre UUID et TEXT qui représentent la même valeur. Contrairement à MySQL ou SQLite qui acceptent des comparaisons mixtes silencieusement, PostgreSQL refuse et lève une erreur explicite. On avait assumé que `source_id` était TEXT, mais la colonne est en fait UUID.
- **Pourquoi c'est intéressant:** C'est une caractéristique de design de PostgreSQL, pas un bug. Ça force la rigueur des types et évite des bugs silencieux de comparaison. La même valeur `a3f2-...` stockée en UUID vs TEXT a des index et comportements différents.
- **Fix:** Comparer UUID à UUID directement (`p.id = e.source_id`) sans cast. Pour le NOT IN: `p.id NOT IN (SELECT source_id FROM ... WHERE ...)` — les deux côtés sont UUID, PostgreSQL accepte.
- **Lesson:** Toujours vérifier les types de colonnes avec `\d table_name` avant d'écrire des JOINs ou des comparaisons. Ne jamais assumer qu'un ID stocké en DB est TEXT — PostgreSQL fait la distinction UUID/TEXT/VARCHAR rigoureusement.

### [BUG-022] Bright Data race condition — status="ready" mais download retourne "building"
- **Date:** 2026-03-05
- **Severity:** High
- **Status:** Fixed
- **Symptom:** `get_status()` retourne `status="ready", size=500` mais `download()` retourne `[{"raw": "Snapshot is building. Try again in a few minutes"}]`. On a perdu ~30 min à créer de nouveaux snapshots inutiles et augmenter les timeouts.
- **Root Cause:** Race condition HTTP 202 documentée dans le SDK lui-même (`utils/polling.py` ligne 127). `base.py download()` sort de sa boucle de polling dès que status="ready" et tente immédiatement le téléchargement. Mais le endpoint de download peut encore retourner "building" quelques secondes/minutes après. `base.py` ne gère pas ce cas (contrairement à `poll_until_ready` qui a un `except DataNotReadyError` pour ça). Résultat: retourne `[{"raw": "Snapshot is building..."}]` sans erreur.
- **Fix:** Bypasser le SDK pour le download — appeler directement `GET https://api.brightdata.com/datasets/snapshots/{snap_id}/download?format=jsonl` avec `Authorization: Bearer TOKEN` via `requests`. Le snapshot READY depuis longtemps est téléchargeable immédiatement ainsi.
- **Lesson:** Quand Bright Data dit `status="ready"`, NE PAS utiliser `client.datasets.X.download()` du SDK. Utiliser requests direct sur l'endpoint REST. Vérifier aussi: ne JAMAIS créer un nouveau snapshot si un ancien existe déjà en status="ready" — le réutiliser.

### [BUG-021] Bright Data snapshot timeout — default 300s insufficient
- **Date:** 2026-03-05
- **Severity:** Medium
- **Status:** Fixed
- **Symptom:** `lake.py --source zillow` fails with `TimeoutError: Snapshot not ready after 300s (status: building)`. SDK reports status `ready` but download still returns `"Snapshot is building. Try again in a few minutes"`.
- **Root Cause:** Bright Data builds dataset snapshots asynchronously. Large datasets (500 records, 18MB) can take 10–15+ minutes to build. The default `timeout=300` in `download()` is too short. Additionally there is a propagation delay between status flipping to `ready` and the data being actually downloadable.
- **Fix:** Increased `timeout` from 300s to 900s (15 min) in all `download()` calls in `lake.py`. The SDK polls every 5s internally.
- **Lesson:** Always use `timeout=900` minimum for Bright Data `download()` calls. Snapshot build time scales with dataset size and server load — never assume 5 min is enough.

---

## Limitations Connues (comportement attendu, pas des bugs)

### [LIM-001] Claude — Knowledge cutoff août 2025
- **Date notée:** 2026-03-06
- **Contexte:** Ce projet tourne en mars 2026. Claude Sonnet 4.6 a un cutoff de données en août 2025.
- **Conséquence pratique:** Claude peut silencieusement "corriger" des versions de modèles, libs ou outils post-août 2025 selon sa connaissance obsolète. Ex: renommer "Gemini Pro 3.0" en "Gemini Pro 2.0" sans avertir.
- **Mitigation:** Toujours spécifier les versions explicitement. Si Claude corrige une version — faire confiance à l'humain, pas à Claude. Pas de blame — limitation de training, pas d'erreur de logique.
- **Note:** Gemini Pro 3.0 présente la même limitation — se présente comme Gemini 2.0 pour la même raison (cutoff dataset identique). Universel aux LLMs, pas spécifique à Claude.

*Last updated: 2026-03-06*
