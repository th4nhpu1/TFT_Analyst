"""Fetch recent VN2 Gold-to-Challenger TFT matches into PostgreSQL.

Usage: python extract/loadData.py --players-per-rank 50 --matches-per-player 20
Credentials are read from environment variables, .env, or ../secret/.env.
"""

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from itertools import zip_longest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def config_value(key):
    if os.environ.get(key):
        return os.environ[key]
    for path in (ROOT / ".env", ROOT.parent / "secret" / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                if name.strip() == key:
                    return value.strip().strip('"').strip("'")
    return None


class RiotClient:
    def __init__(self, token, interval=1.3):
        self.token = token
        self.interval = interval
        self.last_call = 0.0

    def get(self, url):
        for attempt in range(6):
            pause = self.interval - (time.monotonic() - self.last_call)
            if pause > 0:
                time.sleep(pause)
            request = Request(url, headers={
                "X-Riot-Token": self.token,
                "User-Agent": "TFT-Analyst/1.0",
            })
            self.last_call = time.monotonic()
            try:
                with urlopen(request, timeout=20) as response:
                    return json.load(response)
            except HTTPError as error:
                if error.code in (401, 403):
                    raise RuntimeError(f"Riot API returned {error.code}; renew/check RIOT_API_KEY") from error
                if error.code == 429 or 500 <= error.code < 600:
                    retry = error.headers.get("Retry-After")
                    delay = float(retry) if retry else min(2 ** attempt * 5, 120)
                    print(f"Riot returned {error.code}; retrying in {delay:g}s", flush=True)
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"Riot API returned {error.code} for {url.split('?')[0]}") from error
            except (URLError, TimeoutError, ConnectionError) as error:
                if attempt == 5:
                    raise RuntimeError(f"Network error: {getattr(error, 'reason', str(error))}") from error
                delay = min(2 ** attempt * 5, 60)
                print(f"Riot network request interrupted; retrying in {delay}s", flush=True)
                time.sleep(delay)
        raise RuntimeError("Riot API did not recover after retries")


def connect_db(host):
    try:
        import psycopg2
    except ImportError as error:
        raise RuntimeError("Install extract/requirements.txt to use PostgreSQL") from error
    settings = {name: config_value(name) for name in
                ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")}
    missing = [name for name, value in settings.items() if not value]
    if missing:
        raise RuntimeError(f"Missing database settings: {', '.join(missing)}")
    conn = psycopg2.connect(host=host, port=5432, dbname=settings["POSTGRES_DB"],
                            user=settings["POSTGRES_USER"], password=settings["POSTGRES_PASSWORD"])
    with conn.cursor() as cursor:
        cursor.execute("""CREATE TABLE IF NOT EXISTS matches (
            match_id VARCHAR(30) PRIMARY KEY,
            match_data JSONB NOT NULL
        )""")
    conn.commit()
    return conn


def existing_ids(db):
    with db.cursor() as cursor:
        cursor.execute("SELECT match_id FROM matches")
        return {row[0] for row in cursor.fetchall()}


def insert_match(db, match_id, match):
    serialized = json.dumps(match, separators=(",", ":"))
    with db.cursor() as cursor:
        cursor.execute("""INSERT INTO matches (match_id, match_data)
            VALUES (%s, %s::jsonb) ON CONFLICT (match_id) DO NOTHING""",
            (match_id, serialized))
    db.commit()


def main():
    import random
    from rankSampling import TIERS, open_run, sample_players, save_run

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-matches", type=int, default=None, help="Optional cap for a short run; omitted by default")
    parser.add_argument("--players-per-rank", "--players", dest="players", type=int, default=50)
    parser.add_argument("--matches-per-player", type=int, default=20)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--new-sample", action="store_true", help="Start a fresh sample instead of resuming an unfinished run")
    parser.add_argument("--db-host", default=os.getenv("POSTGRES_HOST", "localhost"))
    args = parser.parse_args()
    if min(args.players, args.matches_per_player, args.days) < 1 or (args.max_matches is not None and args.max_matches < 1):
        parser.error("all numeric options must be positive")
    if args.matches_per_player > 100:
        parser.error("--matches-per-player cannot exceed 100")
    key = config_value("RIOT_API_KEY")
    if not key:
        raise RuntimeError("Set RIOT_API_KEY or add it to .env / ../secret/.env")
    client = RiotClient(key)
    db = connect_db(args.db_host)
    run_id = state = None
    try:
        config = dict(players_per_rank=args.players, matches_per_player=args.matches_per_player, days=args.days, tiers=list(TIERS))
        run_id, state = open_run(db, config, args.new_sample)
        save_run(db, run_id, state)
        print(f"Collection {run_id}: {args.players} random players per rank, {args.matches_per_player} recent matches each", flush=True)
        for index, tier in enumerate(TIERS):
            selected = [p for p in state['players'] if p['tier'] == tier]
            if not selected:
                print(f"Sampling {tier} across its ladder...", flush=True)
                selected = sample_players(client, tier, args.players, random.Random(state['seed'] + index))
                state['players'].extend(selected)
                save_run(db, run_id, state)
            print(f"{tier}: {len(selected)} players selected", flush=True)

        for number, player in enumerate(state['players'], 1):
            if player['match_ids'] is None:
                url = (f"https://sea.api.riotgames.com/tft/match/v1/matches/by-puuid/"
                       f"{quote(player['puuid'], safe='')}/ids?{urlencode({'count': args.matches_per_player})}")
                player['match_ids'] = client.get(url)
                save_run(db, run_id, state)
            if number % 25 == 0:
                print(f"Loaded histories for {number}/{len(state['players'])} players", flush=True)

        cutoff_ms = int((datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp() * 1000)
        known = existing_ids(db)
        seen = set(state['processed'])
        fetched = 0
        lists = [p['match_ids'] for p in state['players']]
        state['unique_references'] = len({m for ids in lists for m in ids})
        for group in zip_longest(*lists):
            for match_id in group:
                if match_id is None or match_id in seen:
                    continue
                if match_id not in known:
                    match = client.get(f"https://sea.api.riotgames.com/tft/match/v1/matches/{quote(match_id, safe='')}")
                    info = match.get('info', {})
                    if int(info.get('queue_id', info.get('queueId', 0))) == 1100 and int(info.get('game_datetime', 0)) >= cutoff_ms:
                        insert_match(db, match_id, match)
                        state['saved'] += 1
                        fetched += 1
                seen.add(match_id)
                state['processed'].append(match_id)
                if len(seen) % 25 == 0:
                    save_run(db, run_id, state)
                    print(f"Processed {len(seen)}/{state['unique_references']} unique references; saved {state['saved']} new ranked matches", flush=True)
                if args.max_matches is not None and fetched >= args.max_matches:
                    save_run(db, run_id, state, 'paused')
                    print(f"Paused after saving {fetched} matches; next run resumes this sample", flush=True)
                    return
        save_run(db, run_id, state, 'complete')
        print(f"Complete: {len(state['players'])} sampled players, {state['unique_references']} unique references, {state['saved']} new ranked matches", flush=True)
    except Exception:
        if run_id is not None:
            db.rollback()
            save_run(db, run_id, state, 'failed')
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
