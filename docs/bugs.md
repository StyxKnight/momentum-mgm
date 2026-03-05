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

*Last updated: 2026-03-05*
