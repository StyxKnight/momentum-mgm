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

*Last updated: 2026-03-05*
