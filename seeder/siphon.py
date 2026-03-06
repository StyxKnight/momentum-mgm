"""
Momentum MGM — Siphon (incremental refresh)
Called by systemd timer. Checks last successful run per source,
skips sources that were collected recently enough.

Schedule (enforced here, not in timer):
  indeed      → refresh if last run > 1 day ago
  yelp        → refresh if last run > 7 days ago
  google_maps → refresh if last run > 7 days ago
  zillow      → refresh if last run > 30 days ago
  census      → refresh if last run > 365 days ago
"""

import os
import sys
import subprocess
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [siphon] %(message)s")
log = logging.getLogger("siphon")

DB = {
    "host": "127.0.0.1", "port": 5432,
    "dbname": "momentum", "user": "nodebb", "password": "superSecret123",
}

SCHEDULES = {
    "indeed":               timedelta(days=1),
    "yelp":                 timedelta(days=7),
    "google_maps":          timedelta(days=7),
    "zillow":               timedelta(days=30),
    "montgomery_opendata":  timedelta(days=1),   # 311/permits/fire — données fraîches quotidiennement
    "census":               timedelta(days=365),
}

LAKE_SCRIPT = Path(__file__).parent / "lake.py"
PYTHON      = Path(__file__).parent / "venv" / "bin" / "python3"


def get_last_run(conn, source: str) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT completed_at FROM civic_data.siphon_runs
               WHERE source=%s AND status='success'
               ORDER BY completed_at DESC LIMIT 1""",
            (source,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def should_refresh(last_run: datetime | None, threshold: timedelta) -> bool:
    if last_run is None:
        return True
    age = datetime.now(timezone.utc) - last_run.replace(tzinfo=timezone.utc)
    return age >= threshold


def main():
    conn = psycopg2.connect(**DB)
    now = datetime.now(timezone.utc)
    log.info(f"Siphon started at {now.isoformat()}")

    for source, threshold in SCHEDULES.items():
        last_run = get_last_run(conn, source)
        if not should_refresh(last_run, threshold):
            age = now - last_run.replace(tzinfo=timezone.utc)
            log.info(f"  [{source}] skipping — last run {age.days}d ago (threshold: {threshold.days}d)")
            continue

        log.info(f"  [{source}] refreshing...")
        result = subprocess.run(
            [str(PYTHON), str(LAKE_SCRIPT), "--source", source],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            log.info(f"  [{source}] success")
        else:
            log.error(f"  [{source}] failed:\n{result.stderr[-500:]}")

    conn.close()
    log.info("Siphon complete.")


if __name__ == "__main__":
    main()
