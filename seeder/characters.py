"""
Momentum MGM — Citizen Character Generator
Generates 20 realistic Montgomery AL citizens for Decidim seeding.
Covers all 10 civic categories + Alabama River Corridor Project debate.
Output: /tmp/characters.json
"""
import os, json
from pathlib import Path
from dotenv import load_dotenv
from google import genai as google_genai

load_dotenv(Path(__file__).parent.parent / ".env")
_gemini = google_genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

PROMPT = """Generate exactly 20 realistic citizen profiles for Montgomery, Alabama for a civic participation platform.

CONSTRAINTS:
- Cover all 10 Montgomery neighborhoods: Downtown, West Side, Midtown, East Montgomery, North Montgomery, Garden District, Cloverdale, Maxwell/Gunter, Capitol Heights, Centennial Hill
- At least 2 citizens per neighborhood
- Cover all 10 civic categories across the group: housing, public_safety, economy, governance, transportation, health, education, parks_culture, environment, infrastructure
- Ages range from 22 to 74
- Mix of: Black/African American (~60%), White (~30%), Hispanic/Latino (~10%) — reflecting Montgomery demographics
- Mix of professions: teachers, nurses, pastors, small business owners, retirees, city workers, students, contractors, social workers, mechanics, barbers, etc.
- Communication tones: formal, casual, passionate, analytical, skeptical, community-oriented

MAJOR DIVISIVE PROJECT — "Alabama River Corridor Project":
A proposed $85M highway interchange + commercial corridor through West Montgomery crossing the Alabama River.
- Supporters: see jobs, economic development, better connectivity
- Opponents: fear displacement, environmental damage to Alabama River, gentrification of West Side
- Neutral/mixed: want more information, conditional support
Distribute stances: 7 support, 7 oppose, 6 mixed/conditional

Each citizen has exactly 2-3 civic_concerns from this list (use exact names):
housing, public_safety, economy, governance, transportation, health, education, parks_culture, environment, infrastructure

Return a JSON array of exactly 20 objects with this structure:
{
  "id": 1,
  "first_name": "string",
  "last_name": "string",
  "age": number,
  "gender": "male|female|nonbinary",
  "ethnicity": "Black/African American|White|Hispanic/Latino|Asian|Other",
  "neighborhood": "string (one of the 10 above)",
  "profession": "string",
  "civic_concerns": ["category1", "category2"],
  "tone": "formal|casual|passionate|analytical|skeptical|community-oriented",
  "river_project_stance": "support|oppose|mixed",
  "river_project_reason": "1 sentence explaining their personal reason",
  "bio": "2 sentences about who they are and why they participate civically"
}

Make each citizen feel like a real, distinct person with a believable reason to be on this platform.
Return ONLY the JSON array, no markdown, no explanation."""

print("Generating 20 citizen profiles with Gemini...")
response = _gemini.models.generate_content(
    model="gemini-2.5-flash",
    contents=PROMPT,
    config={"temperature": 0.9, "response_mime_type": "application/json"},
)

raw = response.text.strip()
characters = json.loads(raw)

# Validate
assert len(characters) == 20, f"Expected 20 characters, got {len(characters)}"

# Enrich with Decidim login fields
import random, string
for c in characters:
    slug = f"{c['first_name'].lower()}.{c['last_name'].lower()}".replace(" ", "").replace("'", "")
    c["email"] = f"{slug}@montgomery-civic.sim"
    c["username"] = slug
    c["password"] = "Civic2026!Momentum"

output = "/tmp/characters.json"
with open(output, "w") as f:
    json.dump(characters, f, indent=2, ensure_ascii=False)

print(f"✓ {len(characters)} citizens generated → {output}")
print()

# Summary
from collections import Counter
stances = Counter(c["river_project_stance"] for c in characters)
neighborhoods = Counter(c["neighborhood"] for c in characters)
concerns_flat = [cat for c in characters for cat in c["civic_concerns"]]
concerns = Counter(concerns_flat)

print("River Project stances:", dict(stances))
print("Neighborhoods:", dict(neighborhoods))
print("Civic category coverage:", dict(concerns.most_common()))
print()
for c in characters:
    print(f"  [{c['neighborhood']:20}] {c['first_name']} {c['last_name']:15} ({c['age']}) — {c['profession']:25} | {c['river_project_stance']:7} | {', '.join(c['civic_concerns'])}")
