"""
Momentum MGM — Bright Data Scraper
Collects real civic data from Montgomery, AL public sources.
Output: data/scraped/*.json
"""

import os
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from brightdata import SyncBrightDataClient

load_dotenv(Path(__file__).parent.parent / ".env")

OUTPUT_DIR = Path(__file__).parent / "data" / "scraped"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CATEGORIES = [
    "infrastructure", "environment", "housing", "public_safety",
    "transportation", "health", "education", "economy", "parks_culture", "governance"
]

# Montgomery civic sources to scrape
SOURCES = {
    "mayor_news": {
        "url": "https://www.montgomeryal.gov/Home/Components/News/News/4593/193",
        "description": "Mayor Reed news and announcements"
    },
    "city_311": {
        "url": "https://city-311-citymgm.hub.arcgis.com",
        "description": "Montgomery 311 service portal"
    },
    "open_data": {
        "url": "https://opendata.montgomeryal.gov",
        "description": "City of Montgomery open data portal"
    },
    "budget": {
        "url": "https://cityofmontgomery-al-of.finance.socrata.com",
        "description": "Montgomery open finance / budget"
    },
    "state_of_city": {
        "url": "https://www.montgomeryal.gov/Home/Components/News/News/4818/193",
        "description": "Mayor Reed 2026 State of the City Address"
    },
}

# Search queries to build civic context per category
SEARCH_QUERIES = {
    "infrastructure": "Montgomery Alabama roads bridges infrastructure projects 2025 2026",
    "environment":    "Montgomery Alabama water quality utilities environment flooding 2025 2026",
    "housing":        "Montgomery Alabama housing blight affordable neighborhood 2025 2026",
    "public_safety":  "Montgomery Alabama crime public safety police community 2025 2026",
    "transportation": "Montgomery Alabama transit bus transportation mobility 2025 2026",
    "health":         "Montgomery Alabama public health services homelessness 2025 2026",
    "education":      "Montgomery Alabama schools youth education programs 2025 2026",
    "economy":        "Montgomery Alabama jobs economy small business development 2025 2026",
    "parks_culture":  "Montgomery Alabama parks recreation arts culture 2025 2026",
    "governance":     "Montgomery Alabama city government transparency civic engagement 2026",
}


def save(filename: str, data: dict | list):
    path = OUTPUT_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {path.name} ({len(data) if isinstance(data, list) else 'dict'})")


def scrape_sources(client: SyncBrightDataClient) -> dict:
    """Scrape key Montgomery city pages for civic context."""
    results = {}
    for key, source in SOURCES.items():
        print(f"  Scraping: {source['description']}")
        try:
            result = client.scrape_url(source["url"])
            # Truncate to avoid massive files — first 8000 chars is enough context
            content = result.data[:8000] if isinstance(result.data, str) else str(result.data)[:8000]
            results[key] = {
                "url": source["url"],
                "description": source["description"],
                "content": content,
            }
        except Exception as e:
            print(f"    Warning: {key} failed — {e}")
            results[key] = {"url": source["url"], "description": source["description"], "content": ""}
    return results


def search_civic_context(client: SyncBrightDataClient) -> dict:
    """Run targeted searches per category to gather real Montgomery context."""
    results = {}
    for category, query in SEARCH_QUERIES.items():
        print(f"  Searching: {category}")
        try:
            result = client.search.google(query=query, num_results=8)
            results[category] = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "description": r.get("description", ""),
                }
                for r in result.data
            ]
        except Exception as e:
            print(f"    Warning: {category} search failed — {e}")
            results[category] = []
    return results


def scrape_mayor_priorities(client: SyncBrightDataClient) -> dict:
    """Scrape Mayor Reed's stated priorities and recent statements."""
    print("  Scraping Mayor Reed priorities and State of the City...")
    queries = [
        "Mayor Steven Reed Montgomery Alabama priorities 2026 Momentum",
        "Mayor Reed State of the City 2026 Montgomery address transcript",
        'site:montgomeryal.gov "Reed" 2026 priorities infrastructure safety economy',
    ]
    articles = []
    for q in queries:
        try:
            result = client.search.google(query=q, num_results=5)
            for r in result.data:
                articles.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "description": r.get("description", ""),
                })
        except Exception as e:
            print(f"    Warning: {e}")

    # Also scrape the State of the City page directly
    try:
        page = client.scrape_url("https://www.montgomeryal.gov/Home/Components/News/News/4818/193")
        state_of_city_text = page.data[:6000] if isinstance(page.data, str) else ""
    except Exception:
        state_of_city_text = ""

    return {
        "search_results": articles,
        "state_of_city_text": state_of_city_text,
    }


def scrape_311_categories(client: SyncBrightDataClient) -> list:
    """Get Montgomery 311 service categories — real citizen complaint types."""
    print("  Scraping Montgomery 311 service categories...")
    try:
        result = client.scrape_url("https://city-311-citymgm.hub.arcgis.com")
        content = result.data[:5000] if isinstance(result.data, str) else ""
        # Also search for 311 data
        search = client.search.google(
            query="Montgomery Alabama 311 service request categories types complaints open",
            num_results=6
        )
        return {
            "page_content": content,
            "search_results": [
                {"title": r.get("title",""), "url": r.get("url",""), "description": r.get("description","")}
                for r in search.data
            ]
        }
    except Exception as e:
        print(f"    Warning: 311 scrape failed — {e}")
        return {"page_content": "", "search_results": []}


def main():
    print("Momentum MGM — Bright Data Scraper")
    print("=" * 50)

    with SyncBrightDataClient() as client:
        # 1. Scrape key city pages
        print("\n[1/4] Scraping city pages...")
        sources = scrape_sources(client)
        save("city_pages.json", sources)

        # 2. Search per category
        print("\n[2/4] Searching civic context per category...")
        searches = search_civic_context(client)
        save("category_searches.json", searches)

        # 3. Mayor priorities
        print("\n[3/4] Scraping Mayor Reed priorities...")
        mayor = scrape_mayor_priorities(client)
        save("mayor_priorities.json", mayor)

        # 4. 311 data
        print("\n[4/4] Scraping 311 service data...")
        data_311 = scrape_311_categories(client)
        save("311_data.json", data_311)

    print("\nScraping complete. Files in:", OUTPUT_DIR)
    print("Run seed.py next to populate Decidim.")


if __name__ == "__main__":
    main()
