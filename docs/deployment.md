# Deployment Guide — Momentum MGM

## Prerequisites — What You Need

### Accounts / API Keys

| Service | Status | Notes |
|---|---|---|
| **OpenRouter** | ✅ Have key | Used for Gemini Flash AI classification |
| **Bright Data** | ✅ Have key | Web scraping montgomeryal.gov |
| **Cloudflare** | ✅ Account + tunnel active | Add mgm.styxcore.dev route |
| **GitHub** | ✅ Account | Public repo: StyxKnight/momentum-mgm |
| **Claude Desktop** | ❓ Needed for MCP demo | Install on demo machine |

### Software Already on Server (Raspberry Pi, Debian Bookworm ARM64)

| Software | Version | Status |
|---|---|---|
| Docker | 29.2.1 | ✅ Running |
| Docker Compose | v5.1.0 | ✅ Available |
| Python | 3.11.2 | ✅ Available |
| Node.js | 24.14.0 | ✅ Available |
| Git | — | ✅ Available |
| rbenv / Ruby | Not yet | ❌ To install (Day 1) |

### Docker Containers Already Running

| Container | Image | Purpose for Momentum |
|---|---|---|
| rpg-forum-db | postgres:15-alpine | Add `momentum` database here |
| rpg-forum-redis | redis:7-alpine | Decidim sessions + Sidekiq |
| rpg-nginx | nginx:alpine | Add mgm.styxcore.dev vhost |
| nginx-proxy-manager-app-1 | nginx-proxy-manager | GUI to add proxy host |
| rpg-authelia | authelia/authelia | Protect /admin |

---

## Day 1 — Decidim Installation (ARM64 Native)

### Step 1 — Install Ruby 3.3 via rbenv

```bash
# Install rbenv
curl -fsSL https://github.com/rbenv/rbenv-installer/raw/HEAD/bin/rbenv-installer | bash
echo 'export PATH="$HOME/.rbenv/bin:$PATH"' >> ~/.zshrc
echo 'eval "$(rbenv init -)"' >> ~/.zshrc
source ~/.zshrc

# Install build dependencies (ARM64 Debian Bookworm)
sudo apt-get install -y \
  build-essential libssl-dev libreadline-dev zlib1g-dev \
  libffi-dev libyaml-dev libgmp-dev libgdbm-dev \
  libncurses5-dev libxml2-dev libxslt-dev \
  imagemagick libmagickwand-dev

# Install Ruby 3.3.x (native ARM64, ~15-20 min)
rbenv install 3.3.6
rbenv global 3.3.6
ruby --version   # should print ruby 3.3.x

# Install bundler
gem install bundler
```

### Step 2 — Create PostgreSQL database for Momentum

```bash
docker exec rpg-forum-db psql -U nodebb -c "CREATE DATABASE momentum OWNER nodebb;"
docker exec rpg-forum-db psql -U nodebb -c "CREATE DATABASE momentum_test OWNER nodebb;"
```

### Step 3 — Install Decidim gem and generate app

```bash
# Install decidim CLI (~15-20 min, lots of gems)
gem install decidim

# Generate the app in our project directory
cd /home/styxknight
decidim momentum-app
cd momentum-app
```

### Step 4 — Configure database + Redis

Edit `config/database.yml`:
```yaml
default: &default
  adapter: postgresql
  encoding: unicode
  host: localhost          # PostgreSQL container port-forwarded or host network
  port: 5432
  username: nodebb
  password: superSecret123
  pool: 5

development:
  <<: *default
  database: momentum

production:
  <<: *default
  database: momentum
```

Edit `.env` (create at root):
```bash
REDIS_URL=redis://localhost:6379/1   # rpg-forum-redis, port-forwarded
SECRET_KEY_BASE=<generate with: bundle exec rails secret>
DECIDIM_HOST=mgm.styxcore.dev
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USERNAME=resend
SMTP_PASSWORD=<RESEND_API_KEY>
OPENROUTER_API_KEY=<your key>
BRIGHTDATA_API_KEY=<your key>
```

### Step 5 — Add decidim-polis gem

In `Gemfile`, add:
```ruby
gem "decidim-polis", "~> 0.4"
```

Then:
```bash
bundle install
bundle exec rails decidim_polis:install:migrations
```

### Step 6 — Setup DB and seed

```bash
bundle exec rails db:create db:migrate db:seed
```

### Step 7 — Start Decidim

```bash
# Development
bundle exec rails server -b 0.0.0.0 -p 3000

# Production (with Puma + Sidekiq)
bundle exec puma -C config/puma.rb &
bundle exec sidekiq &
```

### Step 8 — Nginx vhost

Add to Nginx config (via Nginx Proxy Manager GUI or direct file):
```nginx
server {
    listen 80;
    server_name mgm.styxcore.dev;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

### Step 9 — Cloudflare Tunnel

In Cloudflare Zero Trust dashboard, add route:
```
mgm.styxcore.dev → http://localhost:80
```
(Nginx handles the routing to port 3000)

---

## Day 2 — Bright Data Seeder

See [backend.md](backend.md) for seeder setup.

```bash
cd /home/styxknight/momentum-mgm/seeder
pip install -r requirements.txt
cp .env.example .env   # fill BRIGHTDATA_API_KEY, DECIDIM_URL, DECIDIM_TOKEN
python scrape.py       # scrape montgomeryal.gov
python seed.py         # seed proposals into Decidim via GraphQL
```

---

## Day 3 — MCP Server

See [backend.md](backend.md) for MCP server setup.

```bash
cd /home/styxknight/momentum-mgm/mcp-server
pip install -r requirements.txt
cp .env.example .env
python server.py
```

Claude Desktop MCP config (`~/.claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "momentum-mgm": {
      "command": "python",
      "args": ["/home/styxknight/momentum-mgm/mcp-server/server.py"],
      "env": {
        "DECIDIM_URL": "https://mgm.styxcore.dev",
        "DECIDIM_TOKEN": "<admin JWT token>",
        "OPENROUTER_API_KEY": "<your key>"
      }
    }
  }
}
```

---

## Environment Variables Reference

| Variable | Used By | Where to Get |
|---|---|---|
| `OPENROUTER_API_KEY` | MCP Server, Seeder AI | openrouter.ai |
| `BRIGHTDATA_API_KEY` | Seeder scraper | Bright Data dashboard |
| `DECIDIM_TOKEN` | MCP Server, Seeder | Decidim /admin → API tokens |
| `DECIDIM_URL` | MCP Server, Seeder | https://mgm.styxcore.dev |
| `DATABASE_URL` | Decidim | postgres://nodebb:superSecret123@localhost/momentum |
| `REDIS_URL` | Decidim, Sidekiq | redis://localhost:6379/1 |
| `SECRET_KEY_BASE` | Decidim | rails secret |

---

## Port Map

| Port | Service | Notes |
|---|---|---|
| 3000 | Decidim (Puma) | Internal only, Nginx proxies |
| 5432 | PostgreSQL | From rpg-forum-db container |
| 6379 | Redis | From rpg-forum-redis container |
| 8080 | MCP Server | Internal only |
| 80/443 | Nginx | Public via Cloudflare tunnel |

---

*Last updated: 2026-03-05*
