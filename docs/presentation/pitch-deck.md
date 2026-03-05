# Pitch Deck — Momentum MGM

*Hackathon: World Wide Vibes · 5-minute pitch · March 2026*

---

## Slide 1 — Title

**MOMENTUM MGM**
*Civic AI Platform for Montgomery, Alabama*

"Give citizens a voice. Give city hall the tools to listen."

Built during World Wide Vibes Hackathon · March 5–9, 2026
By: Alexandre Breton (StyxKnight)

---

## Slide 2 — The Problem

**Montgomery has no digital channel between citizens and city hall.**

Mayor Reed talks about "Momentum" and "community partnerships" — but it happens through press conferences.

Citizens who want to be heard have no platform. Their concerns get raised at town halls (if they attend), buried in social media, or lost entirely.

City hall has no systematic way to know:
- What issues matter most to residents
- Which neighborhoods are most affected
- How proposals align with the city's own strategic priorities

**The gap is real. The infrastructure doesn't exist.**

---

## Slide 3 — The Solution

**Momentum MGM is a civic participation platform with an AI layer.**

Built on **Decidim** — the same open-source platform used by:
- Barcelona (40,000 participants, 10,000+ proposals)
- Quebec City and Montreal
- Brazil's national government (36,000 proposals processed with AI)

Citizens submit proposals in plain language. The AI classifies them across **10 official civic categories** — the same taxonomy used in 311 systems worldwide: Infrastructure, Environment, Housing, Public Safety, Transportation, Health, Education, Economy, Parks & Culture, and Governance.

The platform shows what Montgomery is actually talking about.

**Critical distinction:** Montgomery already has 311 for *reactive* requests (report a pothole). Momentum MGM is the *proactive* complement — proposals, votes, participation. A Momentum proposal can *trigger* a 311 request. 311 data can *enrich* Momentum. Two halves of a complete civic system.

And the city administrator? They talk to their city through Claude.

---

## Slide 4 — The AI Admin Bridge (The Innovation)

**No existing civic platform has this.**

City admin opens Claude Desktop and asks:
> *"What are citizens saying about public safety this week?"*

Claude calls our MCP server, queries Decidim, and responds:
> *"23 proposals this week. Top cluster: 'Police Response Time in West Montgomery' (11 proposals, high urgency). Second cluster: 'Street Lighting on Southern Blvd' (8 proposals). Recommend escalating to MPD and Public Works. Aligns directly with Reed Priority #1."*

This is Model Context Protocol (MCP) — Anthropic's open standard for connecting AI to external systems. We built the bridge between Claude and civic data.

---

## Slide 5 — The Pol.is Layer

**Inspired by Taiwan's vTaiwan process.**

Pol.is is an opinion clustering tool used in Taiwan to process thousands of citizen opinions and surface genuine consensus — opinions that both sides agree on.

We embed it directly in Decidim participatory processes.

A citizen doesn't just submit a proposal — they can also weigh in on structured questions:
> *"Should Montgomery prioritize housing or road repair this quarter?"*

The visual consensus map becomes a tool for the city to understand, not just count, citizen opinions.

---

## Slide 6 — Live Demo

*[Live demonstration at mgm.styxcore.dev]*

1. Submit a proposal in plain language
2. Watch it classified in real time
3. See the dashboard — what Montgomery is talking about
4. Open Claude Desktop → ask a civic question → see Claude query the platform and advise

---

## Slide 7 — Tech Stack

Built with open-source tools. Minimal ongoing cost.

| Component | Technology |
|---|---|
| Civic Platform | Decidim (Ruby on Rails) |
| Opinion Layer | Pol.is (via decidim-polis) |
| AI Classifier | Gemini Flash via OpenRouter |
| Data | Bright Data (scraped from montgomeryal.gov) |
| Admin Bridge | Anthropic MCP + Claude Desktop |
| Infrastructure | Docker, Nginx, Cloudflare, PostgreSQL 15 |
| Hosting | Self-hosted on styxcore.dev |

**Cost to operate:** ~$20-50/month (hosting + AI API calls at scale)

---

## Slide 8 — Why Montgomery, Why Now

**Envision Montgomery 2040** explicitly calls for increased civic engagement and digital government services.

Mayor Reed's 2026 State of the City theme: **"Momentum"** — building on partnerships and community voice.

This platform:
- Aligns with the city's own stated vision
- Costs nothing to adopt (open source)
- Can be operational in days, not years
- Scales to any city (Decidim runs in 500+ institutions globally)

Montgomery deserves the same tools that Barcelona, Quebec, and Brazil already have. We built it.

---

## Slide 9 — What's Next

If Momentum MGM gets traction:

1. **Pilot with one Montgomery district** — real resident participation
2. **Integration with city systems** — connect proposals to department workflows
3. **Multi-language** — English + Spanish (significant Hispanic population in Montgomery)
4. **Mobile-first** — SMS proposal submission for low-connectivity residents
5. **Open source release** — available for any Alabama municipality to deploy

---

## Slide 10 — Close

**Montgomery is building momentum.**

This is the infrastructure that lets every resident be part of it.

→ **mgm.styxcore.dev**
→ **github.com/StyxKnight/momentum-mgm**

*Questions?*

---

*Last updated: 2026-03-05*
