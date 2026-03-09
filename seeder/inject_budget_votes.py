"""
inject_budget_votes.py
Seed participatory budget votes from 20 simulated citizens.
Each citizen votes based on their civic_concerns profile.
Budget: Montgomery Federal Community Development Allocation 2026 ($2.698M)
"""

import psycopg2
import json
from datetime import datetime, timezone

DB = dict(host="localhost", port=5432, dbname="momentum", user="nodebb", password="superSecret123")

# Projects and their civic themes
PROJECTS = {
    4:  {"title": "Affordable Housing Rehabilitation — Low-Income Homeowners (HOME)", "amount": 852000, "themes": ["housing", "poverty"]},
    5:  {"title": "West Side Streets & Mobility — $36.6M Grant Local Match Support",  "amount": 400000, "themes": ["infrastructure", "transportation"]},
    7:  {"title": "East Fairview & Carter Hill Road Streetscape Implementation",        "amount": 354000, "themes": ["infrastructure", "environment"]},
    9:  {"title": "Urban League Youth Workforce Pipeline — Districts 4, 6, 8",         "amount": 346000, "themes": ["economy", "education"]},
    6:  {"title": "Centennial Hill Food Access & Neighborhood Services",               "amount": 300000, "themes": ["health", "poverty"]},
    10: {"title": "SEED Academy — Emerging Real Estate Developers Program",            "amount": 300000, "themes": ["economy", "housing"]},
    8:  {"title": "Emergency Housing Stability — ESG Rapid Rehousing",                "amount": 146000, "themes": ["housing", "health"]},
    53: {"title": "North Montgomery & Chisholm Housing Stabilization — Emergency Rehab", "amount": 650000, "themes": ["housing", "infrastructure"]},
    54: {"title": "Cottage Hill Blight Elimination & Proactive Code Enforcement",     "amount": 380000, "themes": ["housing", "environment"]},
    55: {"title": "Downtown Montgomery Commercial Corridor — Facade & Public Space",  "amount": 420000, "themes": ["economy", "infrastructure"]},
}

# Citizens and their priorities (from characters.py profile)
CITIZENS = [
    {"id": 155, "concerns": ["housing", "poverty"],          "stance": "support"},
    {"id": 156, "concerns": ["health", "poverty"],           "stance": "mixed"},
    {"id": 157, "concerns": ["economy", "infrastructure"],   "stance": "oppose"},
    {"id": 158, "concerns": ["education", "health"],         "stance": "support"},
    {"id": 159, "concerns": ["housing", "environment"],      "stance": "support"},
    {"id": 160, "concerns": ["infrastructure", "economy"],   "stance": "mixed"},
    {"id": 161, "concerns": ["poverty", "health"],           "stance": "support"},
    {"id": 162, "concerns": ["economy", "education"],        "stance": "oppose"},
    {"id": 163, "concerns": ["housing", "infrastructure"],   "stance": "support"},
    {"id": 164, "concerns": ["health", "environment"],       "stance": "support"},
    {"id": 165, "concerns": ["education", "poverty"],        "stance": "support"},
    {"id": 166, "concerns": ["economy", "housing"],          "stance": "mixed"},
    {"id": 167, "concerns": ["infrastructure", "health"],    "stance": "oppose"},
    {"id": 168, "concerns": ["housing", "poverty"],          "stance": "support"},
    {"id": 169, "concerns": ["economy", "infrastructure"],   "stance": "support"},
    {"id": 170, "concerns": ["health", "education"],         "stance": "mixed"},
    {"id": 171, "concerns": ["housing", "infrastructure"],   "stance": "support"},
    {"id": 172, "concerns": ["poverty", "health"],           "stance": "support"},
    {"id": 173, "concerns": ["economy", "education"],        "stance": "oppose"},
    {"id": 174, "concerns": ["housing", "environment"],      "stance": "support"},
]

BUDGET_ID = 6  # Montgomery Federal Community Development Allocation 2026
TOTAL_BUDGET = 2698000

def get_citizen_projects(concerns, stance, total_budget):
    """Pick projects that match citizen concerns, within total budget."""
    chosen = []
    spent = 0

    # Score each project by theme match
    scored = []
    for pid, proj in PROJECTS.items():
        score = sum(1 for t in proj["themes"] if t in concerns)
        scored.append((score, pid))
    scored.sort(reverse=True)

    # Opponents pick fewer/cheaper projects
    max_projects = 2 if stance == "oppose" else (3 if stance == "mixed" else 4)

    for score, pid in scored:
        if len(chosen) >= max_projects:
            break
        amt = PROJECTS[pid]["amount"]
        if spent + amt <= total_budget:
            chosen.append(pid)
            spent += amt

    return chosen

def inject_votes():
    conn = psycopg2.connect(**DB)
    now = datetime.now(timezone.utc)

    inserted_orders = 0
    inserted_items = 0

    with conn.cursor() as cur:
        # Clean existing votes for this budget
        cur.execute("""
            DELETE FROM decidim_budgets_line_items
            WHERE decidim_order_id IN (
                SELECT id FROM decidim_budgets_orders WHERE decidim_budgets_budget_id = %s
            )
        """, (BUDGET_ID,))
        cur.execute("DELETE FROM decidim_budgets_orders WHERE decidim_budgets_budget_id = %s", (BUDGET_ID,))

        for citizen in CITIZENS:
            uid = citizen["id"]
            concerns = citizen["concerns"]
            stance = citizen["stance"]

            projects = get_citizen_projects(concerns, stance, TOTAL_BUDGET)
            if not projects:
                continue

            # Create order (vote session)
            cur.execute("""
                INSERT INTO decidim_budgets_orders
                    (decidim_user_id, decidim_budgets_budget_id, checked_out_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (uid, BUDGET_ID, now, now, now))
            order_id = cur.fetchone()[0]
            inserted_orders += 1

            # Add line items (chosen projects)
            for pid in projects:
                cur.execute("""
                    INSERT INTO decidim_budgets_line_items (decidim_order_id, decidim_project_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, (order_id, pid))
                inserted_items += 1

            print(f"  Citizen {uid} ({stance}): {[PROJECTS[p]['title'][:40] for p in projects]}")

    conn.commit()
    conn.close()
    print(f"\nDone: {inserted_orders} votes, {inserted_items} line items")

if __name__ == "__main__":
    print("Injecting budget votes...")
    inject_votes()
