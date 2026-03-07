"""
Momentum MGM — Society Seeder
Phase 2: Generates proposals, comments, and meetings for all 20 citizens.
Reads /tmp/characters.json → writes /tmp/society_content.json
"""
import os, json, time
from pathlib import Path
from dotenv import load_dotenv
from google import genai as google_genai

load_dotenv(Path(__file__).parent.parent / ".env")
_gemini = google_genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

def generate(prompt: str, temperature: float = 0.8) -> str:
    r = _gemini.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"temperature": temperature, "response_mime_type": "application/json"},
    )
    return r.text.strip()

# ── Load characters ──────────────────────────────────────────────────────────────
with open("/tmp/characters.json") as f:
    characters = json.load(f)
print(f"Loaded {len(characters)} citizens")

# ── Context shared across all generations ────────────────────────────────────────
MONTGOMERY_CONTEXT = """
Montgomery, Alabama — Real civic context:
- Population: ~200,000. Majority Black/African American (~60%).
- West Side: highest code violations (~10K), fire incidents, poverty. Most affected by Alabama River Corridor Project.
- Centennial Hill: historic Black neighborhood, ADI score 0.938 (most deprived).
- Downtown: revitalization underway, zoning changes, city-owned properties being redeveloped.
- East Montgomery: growing suburb, logistics corridor, transit gaps.
- Maxwell/Gunter AFB: military presence, impacts transportation + economy.
- Real open data sources: 20K fire incidents, 10K code violations, 12.7K business licenses, 1,613 transit stops.
- Alabama River Corridor Project: proposed $85M highway interchange + commercial development
  crossing Alabama River through West Montgomery. City Council vote pending.
  Pro: 2,000 construction jobs, $120M economic impact projection.
  Con: displaces 340 West Side families, threatens Alabama River ecosystem, accelerates gentrification.
"""

RIVER_PROJECT = """
Alabama River Corridor Project details:
- $85M highway interchange + commercial corridor
- Crosses Alabama River at Jeff Davis Ave, through West Montgomery
- Projected: 2,000 temp construction jobs, 800 permanent jobs
- Risk: displaces 340 families, 12 small businesses on West Side
- Environmental: 4.2 miles of Alabama River riparian zone affected
- City Council vote: scheduled March 2026
- Supporters: Downtown Chamber of Commerce, real estate developers, East Montgomery logistics firms
- Opponents: West Side Community Coalition, Alabama Rivers Alliance, historic preservation groups
"""

# ── PHASE 1: Generate proposals ──────────────────────────────────────────────────
print("\n── Phase 1: Generating proposals (2 per citizen = 40 total)...")

PROPOSALS_PROMPT = f"""You are generating realistic citizen proposals for a civic participation platform in Montgomery, Alabama.

{MONTGOMERY_CONTEXT}
{RIVER_PROJECT}

Here are 20 citizens. Generate exactly 2 proposals per citizen (40 total).

Each proposal must:
- Reflect the citizen's concerns, neighborhood, profession, tone, and river project stance
- Use authentic citizen language (not bureaucratic) — match their tone field
- Reference real Montgomery places, streets, or issues when possible
- Be 80-180 words for the body
- Have a clear, specific title (not generic)
- One of the 2 proposals should directly OR indirectly relate to the River Corridor Project for citizens with strong stances
- Category must be one of: housing, public_safety, economy, governance, transportation, health, education, parks_culture, environment, infrastructure

Citizens:
{json.dumps([{
    "id": c["id"],
    "name": f"{c['first_name']} {c['last_name']}",
    "age": c["age"],
    "neighborhood": c["neighborhood"],
    "profession": c["profession"],
    "concerns": c["civic_concerns"],
    "tone": c["tone"],
    "river_stance": c["river_project_stance"],
    "river_reason": c["river_project_reason"],
    "bio": c["bio"]
} for c in characters], indent=2)}

Return a JSON array of exactly 40 objects:
{{
  "character_id": number,
  "character_name": "string",
  "title": "string (specific, compelling, max 80 chars)",
  "body": "string (80-180 words, citizen voice)",
  "category": "string (one of the 10 categories)",
  "tags": ["tag1", "tag2"]
}}

Return ONLY the JSON array."""

if Path("/tmp/proposals.json").exists():
    with open("/tmp/proposals.json") as f:
        proposals = json.load(f)
    print(f"  ✓ Loaded {len(proposals)} proposals from cache")
else:
    raw = generate(PROPOSALS_PROMPT, temperature=0.85)
    proposals = json.loads(raw)
    assert len(proposals) == 40, f"Expected 40 proposals, got {len(proposals)}"
    with open("/tmp/proposals.json", "w") as f:
        json.dump(proposals, f, indent=2, ensure_ascii=False)
    print(f"  ✓ {len(proposals)} proposals generated")
for p in proposals[:5]:
    print(f"    [{p['category']:15}] {p['character_name']:20} — {p['title'][:60]}")
print(f"    ... and {len(proposals)-5} more")
time.sleep(1)

# ── PHASE 2: Generate comments ───────────────────────────────────────────────────
print("\n── Phase 2: Generating comments (3-4 per citizen = ~70 total)...")

# Condensed lists — titles only to keep prompt small
proposal_index = [{"idx": i, "author_id": p["character_id"], "author": p["character_name"],
                   "title": p["title"], "category": p["category"]} for i, p in enumerate(proposals)]
river_props = [p for p in proposal_index if any(
    kw in p["title"].lower() for kw in ["river", "corridor", "displacement", "west side", "highway"]
)]
citizens_mini = [{
    "id": c["id"], "name": f"{c['first_name']} {c['last_name']}",
    "neighborhood": c["neighborhood"], "tone": c["tone"],
    "river_stance": c["river_project_stance"]
} for c in characters]

def comments_batch(batch_citizens, all_proposals, river_props, label):
    cp = f"""Generate citizen comments on civic proposals for Montgomery AL.
River Project: support=pro $85M corridor, oppose=against, mixed=conditional.

These citizens comment (3 each, NOT on their own proposals):
{json.dumps(batch_citizens)}

Available proposals:
{json.dumps(all_proposals)}

River proposals (prioritize for conflict):
{json.dumps(river_props)}

Rules: clash on river proposals when stances differ, 30-70 words per comment, match tone.
Alignment: 1=supports, -1=opposes, 0=neutral.
Total: exactly {len(batch_citizens)*3} comments.

Return JSON array of {len(batch_citizens)*3} objects:
{{"commenter_id":number,"commenter_name":"string","proposal_idx":number,"body":"string","alignment":number}}
Return ONLY the array."""
    raw = generate(cp, temperature=0.8)
    result = json.loads(raw)
    print(f"  ✓ Batch {label}: {len(result)} comments")
    return result

batch_a = citizens_mini[:10]
batch_b = citizens_mini[10:]
comments = comments_batch(batch_a, proposal_index, river_props, "A (citizens 1-10)")
time.sleep(2)
comments += comments_batch(batch_b, proposal_index, river_props, "B (citizens 11-20)")
print(f"  ✓ {len(comments)} total comments generated")
time.sleep(1)

# ── PHASE 3: Generate meetings ───────────────────────────────────────────────────
print("\n── Phase 3: Generating meetings (6 public sessions)...")

MEETINGS_PROMPT = f"""Generate 6 realistic upcoming public meetings for Montgomery, Alabama civic platform.

{MONTGOMERY_CONTEXT}
{RIVER_PROJECT}

Include:
1. Montgomery City Council Regular Session (formal)
2. Public Hearing: Alabama River Corridor Project — Session 1 (high attendance expected)
3. Public Hearing: Alabama River Corridor Project — Session 2 (final before vote)
4. West Montgomery Neighborhood Forum (community-organized)
5. East Montgomery Development & Transportation Committee
6. Parks & Recreation Master Plan Public Consultation

All meetings must be in March-April 2026. Use real Montgomery venues (City Hall, community centers, etc.)

Return a JSON array of 6 objects:
{{
  "title": "string",
  "description": "string (100-200 words — what will be discussed, who should attend)",
  "start_time": "2026-03-XXTXX:XX:00",
  "end_time": "2026-03-XXTXX:XX:00",
  "address": "string (real Montgomery AL address)",
  "location": "string (venue name)",
  "type": "council|hearing|forum|committee|consultation"
}}

Return ONLY the JSON array."""

raw = generate(MEETINGS_PROMPT, temperature=0.6)
meetings = json.loads(raw)
print(f"  ✓ {len(meetings)} meetings generated")
for m in meetings:
    print(f"    [{m['start_time'][:10]}] {m['title'][:60]}")
time.sleep(1)

# ── Save everything ──────────────────────────────────────────────────────────────
output = {
    "characters": characters,
    "proposals": proposals,
    "comments": comments,
    "meetings": meetings,
    "stats": {
        "citizens": len(characters),
        "proposals": len(proposals),
        "comments": len(comments),
        "meetings": len(meetings),
    }
}

with open("/tmp/society_content.json", "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n✓ All content saved → /tmp/society_content.json")
print(f"  Citizens:  {len(characters)}")
print(f"  Proposals: {len(proposals)}")
print(f"  Comments:  {len(comments)}")
print(f"  Meetings:  {len(meetings)}")
print(f"\nNext: ruby seeder/inject_decidim.rb")
