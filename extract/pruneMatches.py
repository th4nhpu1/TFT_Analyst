"""Remove raw TFT matches played more than seven days ago."""

import argparse
import os
from datetime import datetime, timedelta, timezone

from loadData import connect_db


OLD_MATCH_PREDICATE = """
    CASE
        WHEN jsonb_typeof(match_data #> '{info,game_datetime}') = 'number'
        THEN (match_data #>> '{info,game_datetime}')::numeric
    END < %s
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--db-host", default=os.getenv("POSTGRES_HOST", "localhost"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be positive")

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    db = connect_db(args.db_host)
    try:
        with db.cursor() as cursor:
            if args.dry_run:
                cursor.execute(f"SELECT count(*) FROM public.matches WHERE {OLD_MATCH_PREDICATE}", (cutoff_ms,))
                count = cursor.fetchone()[0]
                print(f"Would remove {count} matches played before {cutoff.isoformat()}")
            else:
                cursor.execute(f"DELETE FROM public.matches WHERE {OLD_MATCH_PREDICATE}", (cutoff_ms,))
                count = cursor.rowcount
                db.commit()
                print(f"Removed {count} matches played before {cutoff.isoformat()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
