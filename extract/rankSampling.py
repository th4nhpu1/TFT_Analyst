"""Random rank sampling and resumable collection state in PostgreSQL."""

import random
from uuid import uuid4

TIERS = ("GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER")
DIVISIONS = ("I", "II", "III", "IV")


def sample_players(client, tier, count, rng):
    base = "https://vn2.api.riotgames.com/tft/league/v1"
    if tier in TIERS[-3:]:
        candidates = client.get(f"{base}/{tier.lower()}").get("entries", [])
    else:
        cache = {}

        def page(division, number):
            key = (division, number)
            if key not in cache:
                cache[key] = client.get(f"{base}/entries/{tier}/{division}?page={number}")
            return cache[key]

        # Discover each division's page range instead of sampling only page 1.
        pages = []
        for division in DIVISIONS:
            if not page(division, 1):
                continue
            low, high = 1, 2
            while page(division, high):
                low, high = high, high * 2
                if high > 65536:
                    raise RuntimeError(f"Could not find the end of {tier} {division}")
            while low + 1 < high:
                middle = (low + high) // 2
                if page(division, middle):
                    low = middle
                else:
                    high = middle
            pages.extend((division, number) for number in range(1, low + 1))
        rng.shuffle(pages)
        candidates = []
        # A randomized pool spread across up to 12 pages of the rank.
        for index, (division, number) in enumerate(pages):
            candidates.extend(page(division, number))
            eligible = {e['puuid'] for e in candidates if e.get('puuid')}
            if index >= min(12, len(pages)) - 1 and len(eligible) >= count:
                break
    unique = {e['puuid']: e for e in candidates if e.get('puuid')}
    if len(unique) < count:
        raise RuntimeError(f"{tier}: only {len(unique)} eligible players found; requested {count}")
    return [dict(puuid=e['puuid'], tier=tier, division=e.get('rank'), match_ids=None)
            for e in rng.sample(list(unique.values()), count)]


def open_run(db, config, new_sample=False):
    import json
    with db.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(847331)")
        if not cursor.fetchone()[0]:
            raise RuntimeError("Another match collector is already running")
        cursor.execute("""CREATE TABLE IF NOT EXISTS ingestion_runs (
            run_id text PRIMARY KEY, started_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(), status text NOT NULL,
            config jsonb NOT NULL, state jsonb NOT NULL
        )""")
        if not new_sample:
            cursor.execute("""SELECT run_id, state FROM ingestion_runs
                WHERE config = %s::jsonb AND status IN ('running', 'failed', 'paused')
                ORDER BY started_at DESC LIMIT 1""", (json.dumps(config),))
            row = cursor.fetchone()
            if row:
                db.commit()
                return row
        run_id = str(uuid4())
        state = dict(seed=random.SystemRandom().randrange(2**31), players=[], processed=[], saved=0)
        cursor.execute("INSERT INTO ingestion_runs(run_id, status, config, state) VALUES (%s, 'running', %s, %s)",
                       (run_id, json.dumps(config), json.dumps(state)))
    db.commit()
    return run_id, state


def save_run(db, run_id, state, status='running'):
    import json
    with db.cursor() as cursor:
        cursor.execute("UPDATE ingestion_runs SET state=%s, status=%s, updated_at=now() WHERE run_id=%s",
                       (json.dumps(state), status, run_id))
    db.commit()
