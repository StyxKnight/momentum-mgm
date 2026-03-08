"""
Momentum MGM — Survey Response Injection
Injects realistic survey responses for 20 seeded citizens.
Each citizen answers surveys matching their civic_concerns (~80% participation).
Answers are driven by neighborhood, concerns, and river_project_stance.
"""
import psycopg2
import random
import hashlib
from datetime import datetime, timedelta

random.seed(99)

DB = dict(host="127.0.0.1", port=5432, dbname="momentum", user="nodebb", password="superSecret123")

# ── Questionnaire → civic concern mapping ─────────────────────────────────────
# questionnaire_id → (concern_key, questions_with_options)
# questions: {question_id: [option_ids]} or {question_id: "TEXT:<template>"}
SURVEYS = {
    # Q10 — Housing/CDBG (in Infrastructure process, but housing content)
    10: {
        "concerns": ["housing", "infrastructure", "governance"],
        "questions": {
            38: "single",    # CDBG funds priority
            39: "single",    # Awareness of CDBG
            40: "single",    # Which neighborhood needs investment
            41: "multiple",  # Type of housing program
            42: "text",
        },
        "options": {
            38: [102, 103, 104, 105, 106, 107],
            39: [108, 109, 110, 111],
            40: [112, 113, 114, 115, 116, 117, 118, 119],
            41: [120, 121, 122, 123, 124, 125],
        },
    },
    # Q11 — Parks & Culture
    11: {
        "concerns": ["parks_culture", "environment", "health"],
        "questions": {43: "single", 44: "single", 45: "multiple", 46: "text"},
        "options": {
            43: [126, 127, 128, 129, 130, 131],
            44: [132, 133, 134, 135, 136],
            45: [137, 138, 139, 140, 141, 142, 143],
        },
    },
    # Q12 — Environment
    12: {
        "concerns": ["environment", "health", "housing"],
        "questions": {47: "single", 48: "single", 49: "single", 50: "text"},
        "options": {
            47: [144, 145, 146, 147, 148, 149, 150],
            48: [151, 152, 153, 154, 155],
            49: [156, 157, 158, 159, 160],
        },
    },
    # Q13 — Education
    13: {
        "concerns": ["education", "health", "public_safety"],
        "questions": {51: "single", 52: "single", 53: "single", 54: "text"},
        "options": {
            51: [161, 162, 163, 164],
            52: [165, 166, 167, 168, 169, 170, 171],
            53: [172, 173, 174, 175, 176],
        },
    },
    # Q14 — Transportation
    14: {
        "concerns": ["transportation", "infrastructure", "economy"],
        "questions": {55: "single", 56: "single", 57: "single", 58: "text"},
        "options": {
            55: [177, 178, 179, 180, 181, 182],
            56: [183, 184, 185, 186, 187, 188],
            57: [189, 190, 191, 192, 193, 194],
        },
    },
    # Q15 — Health
    15: {
        "concerns": ["health", "housing", "education"],
        "questions": {59: "single", 60: "multiple", 61: "single", 62: "text"},
        "options": {
            59: [195, 196, 197, 198, 199],
            60: [200, 201, 202, 203, 204, 205, 206],
            61: [207, 208, 209, 210, 211],
        },
    },
    # Q16 — Economy
    16: {
        "concerns": ["economy", "infrastructure", "governance"],
        "questions": {63: "single", 64: "single", 65: "multiple", 66: "text"},
        "options": {
            63: [212, 213, 214, 215, 216, 217],
            64: [218, 219, 220, 221, 222, 223],
            65: [224, 225, 226, 227, 228, 229],
        },
    },
    # Q17 — Infrastructure
    17: {
        "concerns": ["infrastructure", "transportation", "public_safety"],
        "questions": {67: "single", 68: "single", 69: "skip", 70: "text"},
        "options": {
            67: [230, 231, 232, 233, 234],
            68: [235, 236, 237, 238, 239, 240],
        },
    },
    # Q18 — Governance
    18: {
        "concerns": ["governance", "education", "economy"],
        "questions": {71: "single", 72: "single", 73: "multiple", 74: "text"},
        "options": {
            71: [241, 242, 243, 244, 245],
            72: [246, 247, 248, 249, 250, 251],
            73: [252, 253, 254, 255, 256, 257],
        },
    },
    # Q19 — Public Safety
    19: {
        "concerns": ["public_safety", "housing", "environment"],
        "questions": {75: "single", 76: "single", 77: "multiple", 78: "text"},
        "options": {
            75: [258, 259, 260, 261, 262],
            76: [263, 264, 265, 266, 267],
            77: [268, 269, 270, 271, 272, 273, 274],
        },
    },
    # Q20 — Housing
    20: {
        "concerns": ["housing", "economy", "health"],
        "questions": {79: "single", 80: "single", 81: "multiple", 82: "text"},
        "options": {
            79: [275, 276, 277, 278, 279, 280],
            80: [281, 282, 283, 284],
            81: [285, 286, 287, 288, 289, 290, 291],
        },
    },
}

# ── Citizens: user_id + profile ───────────────────────────────────────────────
CITIZENS = [
    {"uid": 155, "name": "Marcus Jenkins",      "hood": "West Side",             "concerns": ["housing", "environment", "public_safety"],   "stance": "oppose",  "income": "low",    "employed": True},
    {"uid": 156, "name": "Latoya Davis",        "hood": "West Side",             "concerns": ["economy", "housing", "transportation"],       "stance": "mixed",   "income": "low",    "employed": True},
    {"uid": 157, "name": "Robert Clark",        "hood": "Downtown",              "concerns": ["governance", "infrastructure", "economy"],    "stance": "support", "income": "high",   "employed": True},
    {"uid": 158, "name": "Sofia Rodriguez",     "hood": "Downtown",              "concerns": ["economy", "parks_culture", "transportation"], "stance": "support", "income": "medium", "employed": True},
    {"uid": 159, "name": "Michael Chen",        "hood": "East Montgomery",       "concerns": ["transportation", "economy", "infrastructure"],"stance": "support", "income": "medium", "employed": True},
    {"uid": 160, "name": "Denise Washington",   "hood": "East Montgomery",       "concerns": ["education", "public_safety", "health"],       "stance": "oppose",  "income": "low",    "employed": True},
    {"uid": 161, "name": "Clarence Montgomery", "hood": "North Montgomery",      "concerns": ["housing", "governance", "public_safety"],     "stance": "oppose",  "income": "low",    "employed": False},
    {"uid": 162, "name": "Brenda Jackson",      "hood": "North Montgomery",      "concerns": ["health", "education", "economy"],             "stance": "mixed",   "income": "low",    "employed": False},
    {"uid": 163, "name": "Steven Miller",       "hood": "Garden District",       "concerns": ["economy", "infrastructure", "housing"],       "stance": "support", "income": "high",   "employed": True},
    {"uid": 164, "name": "Eleanor Vance",       "hood": "Garden District",       "concerns": ["environment", "parks_culture", "governance"], "stance": "oppose",  "income": "high",   "employed": False},
    {"uid": 165, "name": "James Thompson",      "hood": "Cloverdale",            "concerns": ["housing", "infrastructure", "parks_culture"], "stance": "support", "income": "medium", "employed": True},
    {"uid": 166, "name": "Naomi Green",         "hood": "Cloverdale",            "concerns": ["education", "economy", "public_safety"],      "stance": "mixed",   "income": "medium", "employed": True},
    {"uid": 167, "name": "David Nguyen",        "hood": "Maxwell/Gunter",        "concerns": ["transportation", "economy", "public_safety"], "stance": "support", "income": "medium", "employed": True},
    {"uid": 168, "name": "Sarah Peterson",      "hood": "Maxwell/Gunter",        "concerns": ["health", "transportation", "education"],      "stance": "mixed",   "income": "medium", "employed": True},
    {"uid": 169, "name": "Tyrone Bell",         "hood": "Capitol Heights",       "concerns": ["economy", "housing", "public_safety"],        "stance": "oppose",  "income": "low",    "employed": False},
    {"uid": 170, "name": "Carla Ramirez",       "hood": "Capitol Heights",       "concerns": ["education", "parks_culture", "health"],       "stance": "oppose",  "income": "low",    "employed": True},
    {"uid": 171, "name": "Reginald Brooks",     "hood": "Centennial Hill",       "concerns": ["parks_culture", "governance", "environment"], "stance": "mixed",   "income": "low",    "employed": True},
    {"uid": 172, "name": "Gloria Harris",       "hood": "Centennial Hill",       "concerns": ["governance", "housing", "infrastructure"],    "stance": "oppose",  "income": "low",    "employed": False},
    {"uid": 173, "name": "Anthony Scott",       "hood": "Midtown",               "concerns": ["economy", "housing", "transportation"],       "stance": "support", "income": "medium", "employed": True},
    {"uid": 174, "name": "Olivia Wright",       "hood": "Midtown",               "concerns": ["environment", "parks_culture", "public_safety"],"stance": "oppose","income": "medium", "employed": True},
]

# ── Neighbourhood profile → realistic answer biases ──────────────────────────
# Returns biased option index (0-based) based on hood/income

DEPRIVED_HOODS = {"West Side", "North Montgomery", "Capitol Heights", "Centennial Hill"}

def pick_single(options: list, bias_toward_end: bool = False) -> int:
    """Pick one option, biased toward beginning or end of list."""
    if bias_toward_end:
        weights = list(range(len(options), 0, -1))
    else:
        weights = list(range(1, len(options) + 1))
    return random.choices(options, weights=weights, k=1)[0]


def pick_multiple(options: list, min_k=1, max_k=3) -> list:
    k = random.randint(min_k, min(max_k, len(options)))
    return random.sample(options, k)


def get_answer(citizen: dict, qid: int, survey: dict) -> tuple:
    """
    Returns (answer_type, value):
      ('option', option_id)     — single choice
      ('options', [option_ids]) — multiple choice
      ('text', str)             — long text
      ('skip', None)            — skip
    """
    hood = citizen["hood"]
    income = citizen["income"]
    employed = citizen["employed"]
    stance = citizen["stance"]
    concerns = citizen["concerns"]
    deprived = hood in DEPRIVED_HOODS
    qtype = survey["questions"].get(qid)
    opts = survey["options"].get(qid, [])

    if qtype == "skip":
        return ("skip", None)

    if qtype == "text":
        texts = TEXT_RESPONSES.get(qid, ["I appreciate the opportunity to participate in this survey."])
        return ("text", random.choice(texts))

    if qtype == "single":
        # Per-question biased logic
        if qid == 38:  # CDBG priority
            if "housing" in concerns:     return ("option", random.choice([102, 107]))
            if "economy" in concerns:     return ("option", random.choice([104, 105]))
            if "infrastructure" in concerns: return ("option", 103)
            return ("option", random.choice(opts))

        if qid == 39:  # CDBG awareness
            if deprived: return ("option", random.choice([109, 110]))
            return ("option", random.choice([108, 111, 110]))

        if qid == 40:  # Neighborhood needing investment
            nb_map = {
                "West Side": 113, "North Montgomery": 115,
                "Capitol Heights": 112, "Centennial Hill": 112,
                "East Montgomery": 116, "Cloverdale": 117,
            }
            return ("option", nb_map.get(hood, random.choice([112, 113, 114, 115])))

        if qid == 43:  # Parks usage
            if "parks_culture" in concerns: return ("option", random.choice([126, 127, 128]))
            return ("option", random.choice([129, 130, 131]))

        if qid == 44:  # Parks budget cut
            if "parks_culture" in concerns: return ("option", random.choice([132, 135]))
            return ("option", random.choice([133, 134, 136]))

        if qid == 47:  # Env issue
            if deprived:
                return ("option", random.choice([144, 147, 148, 150]))
            return ("option", random.choice([144, 145, 146, 148]))

        if qid == 48:  # Food desert
            if hood in {"West Side", "Capitol Heights", "Centennial Hill"}: return ("option", random.choice([151, 152]))
            if hood in {"North Montgomery"}: return ("option", 153)
            return ("option", random.choice([154, 155]))

        if qid == 49:  # Env participation
            return ("option", random.choice([156, 157, 158]))

        if qid == 51:  # MPS children
            return ("option", random.choice([161, 162, 163]))

        if qid == 52:  # Education priority
            if deprived: return ("option", random.choice([168, 169, 170]))
            return ("option", random.choice([165, 166, 167]))

        if qid == 53:  # Workforce training
            if not employed: return ("option", random.choice([172, 173]))
            return ("option", random.choice([174, 175, 176]))

        if qid == 55:  # Transportation mode
            if "transportation" in concerns and deprived: return ("option", random.choice([178, 180]))
            return ("option", random.choice([177, 179, 182]))

        if qid == 56:  # MAX bus satisfaction
            if "transportation" in concerns and deprived: return ("option", random.choice([186, 187]))
            return ("option", random.choice([183, 184, 185, 188]))

        if qid == 57:  # Transit barrier
            if deprived: return ("option", random.choice([189, 190, 192]))
            return ("option", random.choice([193, 194]))

        if qid == 59:  # Healthcare access
            if income == "low": return ("option", random.choice([197, 198, 199]))
            if income == "medium": return ("option", random.choice([196, 197]))
            return ("option", random.choice([195, 196]))

        if qid == 61:  # Food access
            if deprived: return ("option", random.choice([209, 210]))
            return ("option", random.choice([207, 208]))

        if qid == 63:  # Employment
            if not employed: return ("option", random.choice([215, 216]))
            if income == "high": return ("option", random.choice([212, 214]))
            return ("option", random.choice([212, 213]))

        if qid == 64:  # Economic barrier
            if deprived: return ("option", random.choice([218, 219, 222, 223]))
            return ("option", random.choice([218, 219, 220, 221]))

        if qid == 67:  # Infra condition
            if deprived: return ("option", random.choice([232, 233, 234]))
            return ("option", random.choice([230, 231, 232]))

        if qid == 68:  # Infra problem
            if deprived: return ("option", random.choice([235, 237, 238]))
            return ("option", random.choice([235, 236, 239]))

        if qid == 71:  # City govt satisfaction
            if deprived: return ("option", random.choice([244, 245]))
            return ("option", random.choice([242, 243, 244]))

        if qid == 72:  # Civic participation
            return ("option", random.choice([246, 247, 249, 250, 251]))

        if qid == 75:  # Safety feeling
            if deprived: return ("option", random.choice([260, 261, 262]))
            return ("option", random.choice([258, 259, 260]))

        if qid == 76:  # Police trust
            if deprived: return ("option", random.choice([265, 266]))
            if "public_safety" in concerns: return ("option", random.choice([264, 265]))
            return ("option", random.choice([263, 264]))

        if qid == 79:  # Housing tenure
            if income == "low": return ("option", random.choice([277, 278]))
            if income == "medium": return ("option", random.choice([276, 277]))
            return ("option", random.choice([275, 276]))

        if qid == 80:  # Housing cost burden
            if income == "low": return ("option", random.choice([281, 282]))
            if income == "medium": return ("option", random.choice([282, 283]))
            return ("option", random.choice([283, 284]))

        return ("option", random.choice(opts))

    if qtype == "multiple":
        if qid == 41:  # Housing programs
            base = [120, 123]
            if income == "low": base += [125, 121]
            return ("options", random.sample(base, min(2, len(base))))

        if qid == 45:  # Park improvements
            base = [139, 143]
            if "parks_culture" in concerns: base += [137, 141, 142]
            return ("options", pick_multiple(base, 2, 3))

        if qid == 60:  # Health services gap
            base = [202, 203]
            if income == "low": base += [200, 204]
            if "health" in concerns: base += [201, 205]
            return ("options", pick_multiple(list(set(base)), 2, 3))

        if qid == 65:  # Economic investment
            base = [224, 226]
            if not employed: base += [225, 227]
            if "transportation" in concerns: base += [228]
            return ("options", pick_multiple(list(set(base)), 2, 3))

        if qid == 73:  # Governance improvement
            base = [253, 254, 257]
            if deprived: base += [252, 256]
            return ("options", pick_multiple(list(set(base)), 2, 3))

        if qid == 77:  # Safety solutions
            if deprived: return ("options", pick_multiple([269, 270, 271, 272], 2, 3))
            return ("options", pick_multiple([268, 269, 273, 274], 2, 3))

        if qid == 81:  # Housing programs needed
            base = [287, 289]
            if income == "low": base += [285, 288, 290]
            return ("options", pick_multiple(list(set(base)), 2, 3))

        return ("options", pick_multiple(opts, 1, 2))

    return ("skip", None)


# ── Long response text pools per question ────────────────────────────────────
TEXT_RESPONSES = {
    42: [  # CDBG / housing
        "Montgomery needs to prioritize housing rehab for long-time homeowners in Centennial Hill and West Side before these neighborhoods are lost to blight.",
        "Federal CDBG dollars should follow the data — North Montgomery has the most housing violations. That's where the investment belongs.",
        "We need small business grants on Cleveland Avenue and downtown corridors. Empty storefronts kill neighborhoods faster than anything.",
        "Workforce training tied to real jobs in healthcare and logistics. That's the gap. Skills programs that lead nowhere don't help.",
    ],
    46: [  # Parks
        "We need a functional community center in North Montgomery — the one on Fairview is barely usable.",
        "The riverfront has enormous potential for a multi-use trail. City hall keeps talking about it. Time to build it.",
        "Summer camps saved me as a kid. The cuts to youth programs are a false economy — we'll pay for it in other ways later.",
        "Cultural programming matters for city identity. Montgomery has incredible civil rights history that's underleveraged.",
    ],
    50: [  # Environment
        "The drainage on the West Side floods three times a year. It's been like that since I was a child. Nothing changes.",
        "We need shade trees planted throughout Centennial Hill and Capitol Heights. Extreme heat is a health issue, not just comfort.",
        "Alabama River cleanup is a long-term investment in every neighborhood downstream. You can't develop the waterfront on a polluted river.",
        "The abandoned lots on Hall Street are environmental hazards. Cleanup grants exist — the city just needs to apply.",
    ],
    54: [  # Education
        "After-school programs in East Montgomery kept kids out of trouble and on track. Cutting them is shortsighted.",
        "MPS needs to pay competitive salaries or it will keep losing its best teachers to Autauga and Elmore counties.",
        "Vocational training aligned with Maxwell AFB contractor needs could transform employment outcomes here.",
        "Mental health counselors in every school. Not optional — it's the baseline for kids to be able to learn.",
    ],
    58: [  # Transportation
        "I lost a job because the bus route changed and I couldn't get there. MAX needs to extend hours and Sunday service.",
        "There are no sidewalks between my neighborhood and the nearest grocery store. That's a safety issue and a health issue.",
        "Park-and-ride lots near major employment corridors would help people who live far from downtown.",
        "Bike lanes on Dexter Avenue and the riverfront would change how people experience downtown Montgomery.",
    ],
    62: [  # Health
        "The Centennial Hill area needs a federally qualified health center. The nearest one is too far without a car.",
        "Mental health services are the hidden crisis in Montgomery. Waiting lists are months long.",
        "Food access is the root of half our health problems. We need mobile fresh food markets in food desert zip codes.",
        "Expand Medicaid reimbursement rates so more providers will take patients on it. Provider shortage is the real problem.",
    ],
    66: [  # Economy
        "Small business support on Cleveland Avenue and Upper Wetumpka Road would do more than any big development project.",
        "Logistics and warehousing jobs near Maxwell are real, good-paying jobs. The city should be coordinating workforce pipelines.",
        "Childcare is the hidden employment barrier nobody talks about. One affordable childcare center in North Montgomery would let dozens of parents re-enter the workforce.",
        "Stop subsidizing out-of-state developers and start lending to local entrepreneurs. The money leaves Montgomery as soon as the ribbon is cut.",
    ],
    70: [  # Infrastructure
        "Upper Wetumpka Road is in terrible shape. Potholes damage cars and the city gets liability complaints every month.",
        "The drainage infrastructure under West Montgomery is 60 years old. We need a real capital plan, not patchwork repairs.",
        "Street lighting on the non-commercial streets of North Montgomery and Capitol Heights is inadequate. It's a safety issue.",
        "Fix the basics first. Pothole repair, sidewalk gaps, working streetlights. Then we can talk about big projects.",
    ],
    74: [  # Governance
        "I've never been invited to a budget meeting. The city makes decisions and calls it participation. It's not.",
        "Post all public meeting agendas online at least two weeks out. Most people find out after the fact.",
        "The city should send budget summaries to every household — mail, not just website. Not everyone is online.",
        "We need a real community advisory board with decision-making power, not just input that gets ignored.",
    ],
    78: [  # Public Safety
        "Community policing actually works when it's real. Officers who know the neighborhood by name change the dynamic.",
        "Youth intervention before age 16 is the only prevention strategy that has evidence behind it. Fund it.",
        "Better lighting and maintained properties in vacant lots reduces crime faster than more patrols. The research is clear.",
        "Crisis response shouldn't always mean police. A mobile mental health team would handle 30% of calls better.",
    ],
    82: [  # Housing
        "I've been on the affordable housing waitlist for two years. The demand is real and the supply isn't there.",
        "Home repair grants for seniors and long-term owners in West Side and Centennial Hill should be priority one.",
        "Eviction prevention is cheaper than homelessness. Every dollar in rental assistance saves the city five in shelter and services.",
        "We need zoning reform to allow more mixed-income housing near employment centers. Exclusionary zoning is the problem.",
    ],
}


def fake_session_token(uid: int, qid: int) -> str:
    return hashlib.md5(f"mgm-{uid}-{qid}-sim".encode()).hexdigest()[:32]


def spread_date(base_days_ago: int) -> datetime:
    return datetime.now() - timedelta(
        days=random.randint(0, base_days_ago),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()

    # Clear existing simulation responses
    uids = [c["uid"] for c in CITIZENS]
    cur.execute("DELETE FROM decidim_forms_responses WHERE decidim_user_id = ANY(%s)", (uids,))
    # response_choices cascade via FK? Let's check and clean manually
    cur.execute("""
        DELETE FROM decidim_forms_response_choices
        WHERE decidim_response_id NOT IN (SELECT id FROM decidim_forms_responses)
    """)
    print(f"Cleared existing survey responses.")

    total_responses = 0
    PARTICIPATION_RATE = 0.80  # citizens fill out surveys matching their concerns
    CROSS_PARTICIPATION = 0.25  # and occasionally others

    for citizen in CITIZENS:
        uid = citizen["uid"]
        concerns = set(citizen["concerns"])

        for qid, survey in SURVEYS.items():
            survey_concerns = set(survey["concerns"])
            # Decide if this citizen fills this survey
            if survey_concerns & concerns:
                if random.random() > PARTICIPATION_RATE:
                    continue
            else:
                if random.random() > CROSS_PARTICIPATION:
                    continue

            session_token = fake_session_token(uid, qid)
            ts = spread_date(45)

            for question_id, qtype in survey["questions"].items():
                answer_type, value = get_answer(citizen, question_id, survey)

                if answer_type == "skip" or value is None:
                    continue

                # Insert response row
                cur.execute("""
                    INSERT INTO decidim_forms_responses
                    (body, decidim_user_id, decidim_questionnaire_id, decidim_question_id,
                     created_at, updated_at, session_token)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    value if answer_type == "text" else None,
                    uid, qid, question_id, ts, ts, session_token
                ))
                response_id = cur.fetchone()[0]
                total_responses += 1

                # Insert choice(s) for option questions
                if answer_type == "option":
                    cur.execute("""
                        INSERT INTO decidim_forms_response_choices
                        (decidim_response_id, decidim_response_option_id, position, body)
                        VALUES (%s, %s, 0, '{}')
                    """, (response_id, value))

                elif answer_type == "options":
                    for pos, opt_id in enumerate(value):
                        cur.execute("""
                            INSERT INTO decidim_forms_response_choices
                            (decidim_response_id, decidim_response_option_id, position, body)
                            VALUES (%s, %s, %s, '{}')
                        """, (response_id, opt_id, pos))

    conn.commit()
    print(f"Inserted {total_responses} survey responses across {len(CITIZENS)} citizens.")

    # Summary by questionnaire
    cur.execute("""
        SELECT decidim_questionnaire_id, COUNT(DISTINCT decidim_user_id) as respondents,
               COUNT(*) as total_answers
        FROM decidim_forms_responses
        WHERE decidim_user_id = ANY(%s)
        GROUP BY decidim_questionnaire_id
        ORDER BY decidim_questionnaire_id
    """, (uids,))
    print("\nResponses by survey:")
    for qid, respondents, answers in cur.fetchall():
        print(f"  Questionnaire {qid}: {respondents} respondents, {answers} answers")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
