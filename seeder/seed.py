"""
Momentum MGM — Decidim Seeder
Reads scraped Montgomery data, generates realistic civic proposals via Gemini Flash,
and inserts them into Decidim via GraphQL API.
"""

import os
import json
import time
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from google import genai as google_genai

load_dotenv(Path(__file__).parent.parent / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
RAILS_RUNNER = "/usr/local/bin/decidim-start.sh"
MOMENTUM_APP = "/home/styxknight/momentum-app"

DATA_DIR = Path(__file__).parent / "data" / "scraped"

# Primary: OpenRouter — x-ai/grok-4-fast (fast, cost-effective)
# Fallback: Google Gemini 2.0 Flash direct (requires billing-enabled key)
openrouter = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)
gemini_direct = google_genai.Client(api_key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None


def generate_text(prompt: str) -> str:
    """Generate text — OpenRouter primary, Gemini direct fallback."""
    try:
        r = openrouter.chat.completions.create(
            model="x-ai/grok-4-fast",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
        )
        return r.choices[0].message.content
    except Exception as e:
        if gemini_direct:
            print(f"  OpenRouter failed ({type(e).__name__}), trying Gemini direct...")
            r = gemini_direct.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            return r.text
        raise

CATEGORIES = {
    "infrastructure": {
        "label": "Infrastructure & Roads",
        "slug": "infrastructure",
        "description": "Roads, bridges, sidewalks, street lighting, public works"
    },
    "environment": {
        "label": "Water, Utilities & Environment",
        "slug": "environment",
        "description": "Water quality, sewers, flooding, air quality, environmental concerns"
    },
    "housing": {
        "label": "Housing & Neighborhoods",
        "slug": "housing",
        "description": "Blight, abandoned buildings, affordable housing, neighborhood revitalization"
    },
    "public_safety": {
        "label": "Public Safety",
        "slug": "public-safety",
        "description": "Crime prevention, police-community relations, fire safety, emergency response"
    },
    "transportation": {
        "label": "Transportation & Mobility",
        "slug": "transportation",
        "description": "Public transit, parking, bike lanes, sidewalks, accessibility"
    },
    "health": {
        "label": "Health & Social Services",
        "slug": "health",
        "description": "Public health, mental health, homelessness, social support programs"
    },
    "education": {
        "label": "Education & Youth",
        "slug": "education",
        "description": "Schools, youth programs, libraries, workforce development"
    },
    "economy": {
        "label": "Economy & Employment",
        "slug": "economy",
        "description": "Small business support, job creation, investment, economic equity"
    },
    "parks_culture": {
        "label": "Parks, Culture & Recreation",
        "slug": "parks-culture",
        "description": "Parks, arts, sports facilities, community spaces, cultural heritage"
    },
    "governance": {
        "label": "Governance & Democracy",
        "slug": "governance",
        "description": "Civic processes, budget participation, government transparency"
    },
}

PROPOSALS_PER_CATEGORY = 6


# ── Decidim insertion via Rails runner ───────────────────────────────────────

RAILS_INSERT_SCRIPT = """
require 'json'

proposals_json = File.read(ENV['PROPOSALS_FILE'])
proposals_data = JSON.parse(proposals_json)
org = Decidim::Organization.first
admin = Decidim::User.where(organization: org, admin: true).first

created = 0
proposals_data.each do |entry|
  process = Decidim::ParticipatoryProcess.find_by(slug: entry['slug'], organization: org)
  next puts "SKIP: process not found for slug #{entry['slug']}" unless process

  component = process.components.find_by(manifest_name: 'proposals')
  next puts "SKIP: no proposals component for #{entry['slug']}" unless component

  entry['proposals'].each do |p|
    proposal = Decidim::Proposals::Proposal.new(
      component: component,
      title: { 'en' => p['title'] },
      body: { 'en' => p['body'] }
    )
    proposal.coauthorships.build(
      decidim_author_id: admin.id,
      decidim_author_type: admin.class.name
    )
    if proposal.save
      proposal.update_columns(published_at: Time.current)
      created += 1
      puts "OK: #{p['title'][0..60]}"
    else
      puts "ERR: #{proposal.errors.full_messages.join(', ')}"
    end
  end
end

puts "\\nTotal inserted: #{created}"
"""


def insert_proposals_via_rails(proposals_data: list) -> bool:
    """Write proposals JSON and insert into Decidim via Rails runner."""
    tmp_file = Path("/tmp/momentum_proposals.json")
    with open(tmp_file, "w") as f:
        json.dump(proposals_data, f, ensure_ascii=False)

    script_file = Path("/tmp/momentum_insert.rb")
    with open(script_file, "w") as f:
        f.write(RAILS_INSERT_SCRIPT)

    env = os.environ.copy()
    env["PROPOSALS_FILE"] = str(tmp_file)
    env["RAILS_ENV"] = "production"

    result = subprocess.run(
        [RAILS_RUNNER, "rails", "runner", str(script_file)],
        env=env,
        cwd=MOMENTUM_APP,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    # Filter Spring noise
    for line in output.splitlines():
        if "Spring" not in line and line.strip():
            print("  " + line)
    return result.returncode == 0


# ── Proposal generation via Gemini Flash ─────────────────────────────────────

def load_context() -> dict:
    """Load all scraped Montgomery data as context."""
    context = {}
    for fname in ["category_searches.json", "mayor_priorities.json", "city_pages.json", "311_data.json"]:
        fpath = DATA_DIR / fname
        if fpath.exists():
            with open(fpath) as f:
                context[fname.replace(".json", "")] = json.load(f)
    return context


def build_context_snippet(category_key: str, context: dict) -> str:
    """Extract relevant context for a given category."""
    snippets = []

    # Category-specific search results
    searches = context.get("category_searches", {}).get(category_key, [])
    for r in searches[:4]:
        snippets.append(f"- {r['title']}: {r['description']}")

    # Mayor priorities
    mayor = context.get("mayor_priorities", {})
    for r in mayor.get("search_results", [])[:2]:
        snippets.append(f"- Reed priority: {r['title']}: {r['description']}")

    return "\n".join(snippets) if snippets else "Montgomery, Alabama civic context."


def generate_proposals(category_key: str, category: dict, context: dict) -> list[dict]:
    """Use Gemini Flash to generate realistic civic proposals based on real Montgomery data."""
    context_snippet = build_context_snippet(category_key, context)

    prompt = f"""You are a civic AI assistant helping seed a real citizen participation platform for Montgomery, Alabama.

Category: {category['label']}
Description: {category['description']}

Real Montgomery context (from city news and data):
{context_snippet}

Generate exactly {PROPOSALS_PER_CATEGORY} distinct, realistic citizen proposals for this category.
These should sound like real Montgomery residents writing about real local issues.
Use specific Montgomery references (neighborhoods, streets, landmarks) where appropriate.
Each proposal should be actionable and address a genuine civic concern.

Respond ONLY with a JSON array. Each item must have:
- "title": short proposal title (max 100 chars, no quotes)
- "body": proposal description (150-300 words, written in first person plural "We propose...", "Our neighborhood needs...")

JSON array only, no other text:"""

    text = generate_text(prompt).strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()

    proposals = json.loads(text)
    return proposals[:PROPOSALS_PER_CATEGORY]


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Momentum MGM — Decidim Seeder")
    print("=" * 50)

    # Load scraped context
    print("\nLoading scraped Montgomery data...")
    context = load_context()
    print(f"  Loaded {len(context)} data sources.")

    all_proposals = []
    failures = []

    # Generate proposals for all categories
    for category_key, category in CATEGORIES.items():
        print(f"\n[{category['label']}] Generating {PROPOSALS_PER_CATEGORY} proposals...")
        try:
            proposals = generate_proposals(category_key, category, context)
            all_proposals.append({
                "slug": category["slug"],
                "category": category["label"],
                "proposals": proposals,
            })
            for p in proposals:
                print(f"  + {p['title'][:70]}")
        except Exception as e:
            print(f"  ERROR: {e}")
            failures.append(category_key)
        time.sleep(1)  # respect Gemini rate limits

    print(f"\n{'=' * 50}")
    print(f"Generated proposals for {len(all_proposals)} categories.")
    print("Inserting into Decidim via Rails runner...")

    insert_proposals_via_rails(all_proposals)

    if failures:
        print(f"\nFailed categories: {failures}")
    print(f"\nDone. Check: https://mgm.styxcore.dev")


if __name__ == "__main__":
    main()
