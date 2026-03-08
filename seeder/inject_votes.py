"""
Momentum MGM — Vote Injection Script
Makes the 20 seeded citizens vote on proposals based on:
  - Their civic_concerns (vote on proposals in matching categories)
  - Their river_project_stance (support/oppose/mixed on River Corridor proposals)
  - ~70% random turnout (realistic, not everyone votes on everything)

Run: python inject_votes.py
"""
import psycopg2
import random
from datetime import datetime, timedelta

random.seed(42)  # Reproducible

DB = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "momentum",
    "user": "nodebb",
    "password": "superSecret123",
}

# ── Citizens: Decidim user_id → profile ──────────────────────────────────────
CITIZENS = [
    {"uid": 155, "concerns": ["housing", "environment", "public_safety"],       "stance": "oppose"},
    {"uid": 156, "concerns": ["economy", "housing", "transportation"],           "stance": "mixed"},
    {"uid": 157, "concerns": ["governance", "infrastructure", "economy"],        "stance": "support"},
    {"uid": 158, "concerns": ["economy", "parks_culture", "transportation"],     "stance": "support"},
    {"uid": 159, "concerns": ["transportation", "economy", "infrastructure"],    "stance": "support"},
    {"uid": 160, "concerns": ["education", "public_safety", "health"],           "stance": "oppose"},
    {"uid": 161, "concerns": ["housing", "governance", "public_safety"],         "stance": "oppose"},
    {"uid": 162, "concerns": ["health", "education", "economy"],                 "stance": "mixed"},
    {"uid": 163, "concerns": ["economy", "infrastructure", "housing"],           "stance": "support"},
    {"uid": 164, "concerns": ["environment", "parks_culture", "governance"],     "stance": "oppose"},
    {"uid": 165, "concerns": ["housing", "infrastructure", "parks_culture"],     "stance": "support"},
    {"uid": 166, "concerns": ["education", "economy", "public_safety"],          "stance": "mixed"},
    {"uid": 167, "concerns": ["transportation", "economy", "public_safety"],     "stance": "support"},
    {"uid": 168, "concerns": ["health", "transportation", "education"],          "stance": "mixed"},
    {"uid": 169, "concerns": ["economy", "housing", "public_safety"],            "stance": "oppose"},
    {"uid": 170, "concerns": ["education", "parks_culture", "health"],           "stance": "oppose"},
    {"uid": 171, "concerns": ["parks_culture", "governance", "environment"],     "stance": "mixed"},
    {"uid": 172, "concerns": ["governance", "housing", "infrastructure"],        "stance": "oppose"},
    {"uid": 173, "concerns": ["economy", "housing", "transportation"],           "stance": "support"},
    {"uid": 174, "concerns": ["environment", "parks_culture", "public_safety"],  "stance": "oppose"},
]

# ── Proposals by category ─────────────────────────────────────────────────────
# Regular proposals (non-River-Corridor) by civic category
REGULAR = {
    "infrastructure": [52, 53, 54, 55, 56, 57],
    "environment":    [58, 59, 60, 61, 62, 63, 151],
    "housing":        [64, 65, 66, 67, 68, 69, 129],
    "public_safety":  [70, 71, 72, 73, 74, 75],
    "transportation": [76, 77, 78, 79, 80, 81, 119],
    "health":         [82, 83, 84, 85, 86, 87, 127, 139],
    "education":      [88, 89, 90, 91, 92, 93, 123],
    "economy":        [],
    "parks_culture":  [],
    "governance":     [],
}

# River Corridor proposals split by position
RIVER_PRO  = [116, 120, 132, 133, 136, 137]  # support economic dev / connectivity
RIVER_ANTI = [112, 113, 122, 124, 130, 138, 141, 147, 150]  # oppose: displacement / environment

TURNOUT = 0.70  # 70% chance any given citizen votes on a relevant proposal


def spread_date(base_days_ago: int) -> datetime:
    """Random timestamp spread over the past N days for realism."""
    offset = timedelta(
        days=random.randint(0, base_days_ago),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    return datetime.now() - offset


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()

    # Clear existing votes from our simulation users only
    uids = [c["uid"] for c in CITIZENS]
    cur.execute(
        "DELETE FROM decidim_proposals_proposal_votes WHERE decidim_author_id = ANY(%s)",
        (uids,)
    )
    print(f"Cleared existing votes for {len(uids)} citizens.")

    votes = []

    for citizen in CITIZENS:
        uid = citizen["uid"]
        concerns = citizen["concerns"]
        stance = citizen["stance"]

        # ── Regular proposals: vote on proposals matching concerns ─────────
        for category in concerns:
            for pid in REGULAR.get(category, []):
                if random.random() < TURNOUT:
                    votes.append((pid, uid, spread_date(60)))

        # ── River Corridor: vote based on stance ──────────────────────────
        if stance == "support":
            # Supporters vote YES on pro-river proposals, occasionally abstain on anti
            for pid in RIVER_PRO:
                if random.random() < 0.85:
                    votes.append((pid, uid, spread_date(45)))
            for pid in RIVER_ANTI:
                if random.random() < 0.10:  # rarely vote on opposition proposals
                    votes.append((pid, uid, spread_date(45)))
        elif stance == "oppose":
            # Opponents vote YES on anti-river proposals, rarely on pro
            for pid in RIVER_ANTI:
                if random.random() < 0.85:
                    votes.append((pid, uid, spread_date(45)))
            for pid in RIVER_PRO:
                if random.random() < 0.10:
                    votes.append((pid, uid, spread_date(45)))
        else:  # mixed
            # Mixed: moderate engagement on both sides
            for pid in RIVER_PRO + RIVER_ANTI:
                if random.random() < 0.40:
                    votes.append((pid, uid, spread_date(45)))

    # Deduplicate (proposal_id, author_id) pairs
    seen = set()
    deduped = []
    for pid, uid, ts in votes:
        key = (pid, uid)
        if key not in seen:
            seen.add(key)
            deduped.append((pid, uid, ts))

    # Insert all votes
    cur.executemany(
        """INSERT INTO decidim_proposals_proposal_votes
           (decidim_proposal_id, decidim_author_id, created_at, updated_at, temporary)
           VALUES (%s, %s, %s, %s, false)
           ON CONFLICT (decidim_proposal_id, decidim_author_id) DO NOTHING""",
        [(pid, uid, ts, ts) for pid, uid, ts in deduped]
    )

    conn.commit()
    print(f"Inserted {len(deduped)} votes across {len(CITIZENS)} citizens.")

    # Show distribution
    cur.execute("""
        SELECT p.decidim_proposal_id, COUNT(*) as votes
        FROM decidim_proposals_proposal_votes p
        WHERE p.decidim_author_id = ANY(%s)
        GROUP BY p.decidim_proposal_id
        ORDER BY votes DESC LIMIT 15
    """, (uids,))
    print("\nTop 15 proposals by vote count:")
    for pid, cnt in cur.fetchall():
        print(f"  Proposal {pid}: {cnt} votes")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
