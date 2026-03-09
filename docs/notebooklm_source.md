# Momentum MGM — Source Document for NotebookLM
## Civic AI Platform for Montgomery, Alabama
### World Wide Vibes Hackathon — March 2026

---

## The Problem We're Solving

Montgomery, Alabama is a city of 200,000 people with no digital channel between its citizens and city hall. If you have a problem with your street, your neighborhood, your water — you have no structured way to tell the city. There's no platform where citizens can propose solutions, vote on priorities, and see their input actually shape policy.

This isn't just a Montgomery problem. It's a global one. But other cities have solved it. And we built what they built — and went further.

---

## What Other Cities Did (And What They Missed)

**Barcelona, Spain** launched Decidim in 2016 — an open-source civic participation platform. Over 10,000 citizen proposals were submitted. Those proposals directly shaped the city's strategic plan. Today Decidim is used by over 450 organizations in 30+ countries. But Barcelona's Decidim has no AI layer. The city still reads proposals manually.

**Brazil** launched Brasil Participativo in 2024. 1.5 million registered citizens. 8,254 proposals for the national 2024–2027 budget plan. 76% of those proposals were incorporated into the real national budget. The government of Brazil is now building an AI system to process citizen input at scale — it was supposed to launch in early 2026. They are still building it.

**Taiwan** used vTaiwan and Pol.is — digital deliberation tools that used AI to find consensus across large groups. 28+ policy cases were deliberated. 80% resulted in real government action. But Taiwan's model doesn't integrate city-level open data. It's about consensus-finding, not civic intelligence.

**What all three have in common:** they proved that digital civic participation works at scale and changes real policy. **What none of them have:** a live AI layer connected to real city data that processes citizen proposals automatically, identifies underserved neighborhoods from evidence, and produces actionable intelligence that flows directly into city hall's existing tools.

**Brazil is still building toward this. We shipped it in 5 days.**

---

## What Momentum MGM Is

Momentum MGM is a three-layer civic AI platform built specifically for Montgomery, Alabama.

### Layer 1: The Citizen Platform

The citizen platform is built on Decidim — the same open-source software used by Barcelona. It runs live at mgm.styxcore.dev on a Raspberry Pi 5 ARM64 server.

Citizens can:
- Submit proposals across 10 civic categories: housing, economy, environment, public safety, health, infrastructure, workforce, transportation, education, parks and culture, governance
- Vote on proposals from other citizens
- Comment and debate
- Participate in structured surveys
- Vote on participatory budgets — where citizens decide how a portion of city money gets spent
- Attend and follow public meetings and assemblies

For the demo, we seeded a simulated civic society: 20 fictional Montgomery citizens, 40 proposals covering all categories, 60 comments, 6 public meetings, and an active participatory budget. These citizens are clearly marked as simulation. In a real deployment they would be replaced by actual Montgomery residents. The AI tools remain active regardless.

### Layer 2: The Civic Data Lake

Behind the platform sits a data lake of 80,000+ real records from Montgomery, Alabama. This is not simulated. This is real city data pulled from official sources.

**From Montgomery's ArcGIS Open Data portal (19 sources):**
- 20,000 fire incident records
- 10,000 code violation records
- 5,619 building permits
- 5,561 housing condition assessments
- 12,751 active business licenses
- 2,005 zoning decisions
- 1,613 transit stops
- 1,337 food safety inspections
- 681 city-owned properties
- 330 environmental nuisance reports
- 319 historic markers
- Parks, recreation areas, community centers, education facilities, behavioral health centers, opportunity zones, infrastructure projects, and more

**From the US Census Bureau (American Community Survey, 2012–2024):**
- 11,334 rows of demographic data
- 71 census tracts covering all of Montgomery County
- 13 metrics per tract per year: median income, poverty rate, unemployment, housing vacancy, median rent, owner vs renter occupancy, education attainment, labor force size
- 14 years of data = time series for trend analysis

**From Bright Data (private web data):**
- 1,561 Yelp business listings in Montgomery: ratings, review counts, closure status, categories
- 500 Zillow property listings: prices, square footage, days on market, neighborhood

**Embeddings:**
- 61,000 vector embeddings generated with Google's gemini-embedding-001 model (3072 dimensions)
- Every record in the data lake has been converted to a semantic vector
- Stored in PostgreSQL with pgvector extension
- Enables semantic similarity search: ask "abandoned buildings near schools" in plain language and get real results

### Layer 3: The MCP Server — The AI Bridge

The MCP server is the soul of Momentum MGM. MCP stands for Model Context Protocol — it's a standard developed by Anthropic that lets AI models like Claude call external tools during a conversation. Instead of just answering from training data, Claude can call live functions that query real databases, analyze real data, and write back to real systems.

Our MCP server has 22 tools. It runs at mcp.styxcore.dev/mcp. Anyone with Claude can add this URL in their settings and immediately have access to Montgomery's civic intelligence layer.

The server is organized in a strict pipeline where each layer feeds the next:

**DETECT tools** (pure SQL, no AI, instant):
- get_census_trend: runs OLS linear regression on 14 years of Census data per neighborhood, returns slope, R², current value, 2026 projection
- get_city_incidents: queries ArcGIS data for any of 19 sources, filtered by neighborhood
- get_business_health: Yelp data — closure rate, average rating, foot traffic proxy, top business categories
- get_job_market: unemployment rate, median household income, education attainment, poverty rate — all compared to city-wide averages in real time

**ANALYZE tools** (mathematical computation, no AI):
- analyze_neighborhood: computes three composite deprivation indices — ADI (Area Deprivation Index from University of Wisconsin/HRSA), SVI (Social Vulnerability Index from CDC/ATSDR), and EJI (Environmental Justice Index from EPA). Each neighborhood gets a z-score normalized score from 0 to 1, higher means worse, percentile-ranked against all 71 census tracts in Montgomery County
- detect_civic_gaps: identifies "silent zones" — neighborhoods with high ArcGIS incident density but zero citizen proposals on Decidim. The gap score is calculated as incident_load divided by max(1, proposals). These are the neighborhoods that need the most help but have the least voice

**REPORT tools** (Gemini 2.5 Flash — this is where AI generates content):
- civic_report: aggregates all DETECT + ANALYZE outputs, pulls Zillow housing data, pulls citizen survey signals from Decidim, then sends everything to Google's Gemini 2.5 Flash model with a Jinja2 RAG prompt and Chain of Thought reasoning. The AI is instructed to cite specific numbers from the data, never invent anything, and output structured JSON with findings, severity levels, and confidence ratings. Covers all 10 civic categories
- find_solutions: runs 3 parallel Brave Search queries (federal programs, global best practices for comparable cities, Montgomery-specific recommendations), combines real search results with Census statistics, and sends to Gemini 2.5 Flash to identify actual active federal grant programs with real URLs and dollar amounts

**CITIZEN VOICE tools** (Decidim GraphQL):
- get_proposals: live citizen proposals from the platform
- get_budget_results: participatory budget voting results — which projects citizens voted to fund, vote counts, voter turnout, funding gaps
- get_meetings: upcoming and past public meetings from Decidim
- summarize_comments: AI reads all comments on a proposal, extracts sentiment, themes, support level, main concerns

**ACT tools** (Decidim write — Gemini inside):
- post_ai_response: closes the full civic loop — fetches a citizen proposal, classifies it, pulls a civic_report for the neighborhood, finds the next public meeting, generates a grounded 3-4 sentence response with real neighborhood data, posts it on Decidim as "Momentum AI"
- post_debate_summary: generates AI syntheses of debate threads on the platform

**OUTPUT tools** (agnostic formatters — no AI inside, receive data from AI tools):
- create_report_doc: formats civic_report + find_solutions outputs into a Google Doc
- create_report_slides: formats key findings into a Google Slides presentation
- export_to_sheet: pushes neighborhood data to Google Sheets
- sync_gcal: syncs Decidim public meetings to Google Calendar
- create_action_tasks: converts recommendations to Google Tasks

**ORCHESTRATOR**:
- create_full_demo: runs the entire pipeline from DETECT to OUTPUT, makes all files publicly accessible, returns all links in one call

---

## What Makes This Different

### The Architecture Decision

Every other civic AI project we've seen tries to do one of two things: either build a chatbot on top of a database, or add AI summarization to an existing platform. We did something structurally different.

We separated concerns cleanly. The data tools never invent anything — they're pure SQL. The analysis tools do math. Only the REPORT layer calls AI, and when it does, it has verified facts as input. The output tools format, they don't generate. This means the AI is grounded at every step.

### Real Data, Not Synthetic

Every number in a civic_report comes from a real record in the database. The system is instructed — at the prompt level — to never infer, never hallucinate, never estimate. If the data isn't there, it says so.

### The Feedback Loop

When a citizen posts a proposal on Decidim, post_ai_response can automatically respond with a grounded comment that cites real neighborhood data. The AI reads the proposal, classifies it, looks up what the data says about that neighborhood, finds the next public meeting where it could be discussed, and writes a response. This closes the loop between citizen input and city intelligence.

### Private Data Integration

Montgomery's open data doesn't tell you which businesses are struggling or what properties are worth. We used Bright Data to pull Yelp business data and Zillow property listings for Montgomery. This private data feeds the Area Deprivation Index calculations and the business health analysis. It's what makes the economic analysis real.

### The Raspberry Pi Constraint

Everything runs on a single Raspberry Pi 5 with 8GB of RAM and an NVMe SSD. Decidim (Ruby on Rails), PostgreSQL with 80,000+ records and 61,000 vector embeddings, the MCP server, the data pipeline, all served through Cloudflare tunnels. This is a deliberate choice — it proves the system can be deployed cheaply anywhere. A mid-sized city doesn't need enterprise infrastructure to run civic AI.

---

## Digital Sovereignty

Momentum MGM runs entirely on a Raspberry Pi 5 with 8GB of RAM and an NVMe SSD, in a living room, served through a Cloudflare tunnel. This is not a limitation — it's a design principle.

**No cloud dependency.** The civic platform, the database, the AI bridge, the data pipeline — all of it runs on hardware that costs $120. A city government, a community organization, or a neighborhood association can deploy this without an AWS account, without a Google Cloud contract, without a Microsoft Azure subscription. The infrastructure bill is approximately $0/month beyond the hardware.

**Citizen data stays local.** On a cloud platform, citizen proposals, voting patterns, and demographic data get stored on servers owned by corporations in other jurisdictions. On Momentum MGM, the data lives on a machine the operator controls. For city governments that have legal obligations around citizen data privacy — or communities with good reasons to distrust centralized infrastructure — this matters.

**Replicable anywhere.** The Raspberry Pi 5 proves the floor. Any city with $120 and a broadband connection can run this. The architecture scales up — you can move the database to a bigger server, add replicas, use a real rack — but you never *have* to. A community of 10,000 people in rural Alabama can run the same civic AI stack as a neighborhood in Montreal.

**Digital agility.** Because there's no cloud vendor, there's no migration cost, no SLA negotiation, no multi-year contract. The system is updated with a `git pull`. It's restarted with `systemctl restart`. It's backed up with `pg_dump`. The entire operational model fits in one person's head.

The limitation is real: a single Raspberry Pi has bounded traffic capacity. Under serious production load — thousands of concurrent users — it would need to scale. But for a city the size of Montgomery deploying this to real citizens, with proper load management and caching, it's viable. And the architecture is containerizable and cloud-deployable when needed. The sovereignty choice is reversible. The vendor lock-in on a proprietary platform is not.

---

## The Innovations We Built This Week

**Day 1 (March 5):** Decidim deployed from scratch on ARM64 — not trivial, required custom Ruby compilation. Live at mgm.styxcore.dev.

**Day 2 (March 6):** Full data pipeline. ArcGIS REST API for 80K city records, Census ACS API for 14 years of demographics, Bright Data for Yelp and Zillow. 61K vector embeddings generated with Gemini.

**Day 3 (March 7):** MCP server with 15 tools. The civic loop closed for the first time — a citizen proposal triggered AI analysis which posted a grounded comment back on Decidim. Simulated civic society seeded.

**Day 4 (March 8):** Google Workspace integration. MCP HTTP transport live. Tools tested end-to-end.

**Day 5 (March 9):** get_job_market tool added — Census workforce analysis with city comparisons. civic_report expanded to cover all 10 civic categories (was missing transportation, education, parks, governance even though the data existed). get_job_market added. civic_report expanded to all 10 civic categories. create_full_demo orchestrator built. Pipeline architecture refactored — output tools enforced as agnostic formatters with no AI inside. Yelp expanded to 1,561 businesses. 22 tools total.

---

## The Soul of the Project

Montgomery is the birthplace of the American civil rights movement. Rosa Parks. The Montgomery Bus Boycott. Selma. These events happened because ordinary people found a way to make their voice count against a system that didn't want to hear them.

Momentum MGM is a bet that technology can restore that connection — that a city where citizens have been historically excluded from power can use the same AI tools that powerful institutions use, and use them to speak truth to those institutions with data.

The Barcelona model proved it works. The Brazil model proved it scales. The Taiwan model proved AI can find consensus. Momentum MGM proves you can do all three, on a Raspberry Pi, for any mid-sized city in America, and you can do it in five days.

The AI isn't replacing civic engagement. It's amplifying it. When a resident in Centennial Hill — a neighborhood where 40% of people live below the poverty line and median income is $40K against a city average of $64K — submits a proposal about housing conditions, Momentum MGM reads the same data that a policy analyst with a PhD and six months would read, and it responds in seconds with grounded evidence from federal programs that could actually help.

That's the soul of it. The city has the data. The citizens have the voice. The AI connects them.

---

## Technical Glossary

**Decidim** — Open-source participatory democracy platform built in Ruby on Rails. Used by Barcelona, Helsinki, NYC, and 450+ organizations globally. Supports proposals, voting, participatory budgeting, meetings, surveys, debates, and assemblies.

**MCP (Model Context Protocol)** — Standard developed by Anthropic for connecting AI models to external tools. Instead of just generating text from training data, Claude can call live functions, query databases, and take actions in external systems during a conversation.

**RAG (Retrieval-Augmented Generation)** — AI technique where relevant data is retrieved from a database and injected into the AI's prompt before generation. This grounds the AI's output in verified facts rather than training data.

**pgvector** — PostgreSQL extension for storing and querying vector embeddings. Enables semantic similarity search across large datasets.

**ADI (Area Deprivation Index)** — Developed by University of Wisconsin and HRSA. Measures material deprivation at the neighborhood level using Census data: income, poverty, employment, housing quality, education. Score 0-1, higher = more deprived.

**SVI (Social Vulnerability Index)** — Developed by CDC/ATSDR. Measures a community's ability to withstand shocks (disasters, disease outbreaks). Uses Census variables across 4 themes: socioeconomic status, household composition, minority status/language, housing/transportation. We exclude Theme 3 (racial composition) to avoid circular reasoning with race as a deprivation variable.

**EJI (Environmental Justice Index)** — Developed by CDC/ATSDR and EPA. Measures cumulative environmental burden including pollution, hazardous sites, air quality, water quality, plus social vulnerability.

**OLS (Ordinary Least Squares)** — Linear regression method used in get_census_trend to fit a line through 14 years of Census data. Returns slope (direction and speed of change), R² (confidence in the trend), and a 2026 projection.

**Gemini 2.5 Flash** — Google's fast, efficient AI model used as primary for all AI generation in Momentum MGM. Called directly via Google GenAI API at temperature 0.1 for analysis (factual, low creativity) and 0.4 for solutions (slightly more generative).

**Grok-4** — xAI's model used as fallback via OpenRouter when Gemini is unavailable.

**FastMCP** — Python library for building MCP servers. Supports both stdio transport (for Claude Desktop) and streamable-HTTP transport (for Claude.ai web/mobile).

**Cloudflare Tunnel** — Zero-trust networking service that exposes local servers to the internet without opening firewall ports. Used to serve mgm.styxcore.dev and mcp.styxcore.dev from a home Raspberry Pi.

**ArcGIS** — Geographic information system platform used by Montgomery city government to publish open data. We pull from the ArcGIS REST FeatureServer API.

**Census ACS (American Community Survey)** — Annual survey by the US Census Bureau producing detailed demographic and economic statistics at the census tract level. 5-year estimates cover ~71 tracts in Montgomery County.

**Bright Data** — Web data platform providing structured access to private data sources (Yelp, Zillow, LinkedIn, Google Maps) through dataset APIs and web unlocker infrastructure.

**Jinja2** — Python templating engine used for the civic_report and find_solutions prompts. Allows complex, conditional prompt construction with loops, includes, and variable injection.

