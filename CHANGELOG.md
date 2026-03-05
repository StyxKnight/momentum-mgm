# Changelog

All notable changes to Momentum MGM, day by day.

---

## [Day 1 — 2026-03-05] Foundation + Architecture

### Added
- Repository initialized with professional structure
- Full documentation suite:
  - `README.md` — project overview with proof of concept table
  - `docs/architecture.md` — full system diagram, tech stack decisions, RAM budget
  - `docs/deployment.md` — complete install guide for Decidim on ARM64 Debian
  - `docs/backend.md` — MCP server tools + seeder architecture
  - `docs/presentation/pitch-deck.md` — full 10-slide hackathon pitch
  - `docs/bugs.md` — bug tracker template
  - `docs/data.md` — data layer reference
  - `docs/api.md` — Decidim GraphQL reference
- Branch strategy and commit conventions in `CONTRIBUTING.md`

### Architecture Decisions Made
- **Decidim over custom FastAPI** — use the proven platform, add AI layer on top
- **Native ARM64 install** — Decidim Docker image is amd64-only; Ruby 3.3 runs natively on ARM64 Debian, ~1h install
- **Pol.is integration** — `decidim-polis` gem embeds opinion clustering in processes; inspired by Taiwan's vTaiwan
- **MCP (Anthropic protocol)** — admin bridge via Claude Desktop; Claude calls tools to query and advise on civic data
- **Existing infrastructure reused** — PostgreSQL, Redis, Nginx, Authelia, Cloudflare tunnel all already running

### Infrastructure Confirmed
- PostgreSQL 15 (rpg-forum-db) ✅ — will add `momentum` database
- Redis 7 (rpg-forum-redis) ✅ PONG — Decidim/Sidekiq will use this
- Nginx + Nginx Proxy Manager ✅ — add mgm.styxcore.dev vhost
- Authelia ✅ healthy — protect /admin
- Cloudflare tunnel ✅ active — add mgm. route
- Available RAM: 5.4GB / 7.9GB ✅ — Decidim needs ~1GB

### Next: Day 2
- [ ] Install rbenv + Ruby 3.3 on Pi (ARM64)
- [ ] `gem install decidim` + generate app
- [ ] Create `momentum` PostgreSQL database
- [ ] Configure DB + Redis + run migrations
- [ ] Add decidim-polis gem
- [ ] Nginx vhost + Cloudflare route
- [ ] First Decidim admin login working at mgm.styxcore.dev

---

<!-- Template:

## [Day N — YYYY-MM-DD] Theme

### Added
-

### Changed
-

### Fixed
-

### Decisions
-

### Next
- [ ]

-->
