"""Fetch recent VN2 Challenger TFT matches into PostgreSQL.

Usage: python extract/loadData.py --max-matches 200
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
            except URLError as error:
                if attempt == 5:
                    raise RuntimeError(f"Network error: {error.reason}") from error
                time.sleep(min(2 ** attempt * 5, 60))
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-matches", type=int, default=1000)
    parser.add_argument("--players", type=int, default=100)
    parser.add_argument("--matches-per-player", type=int, default=20)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--db-host", default=os.getenv("POSTGRES_HOST", "localhost"))
    args = parser.parse_args()
    if min(args.max_matches, args.players, args.matches_per_player, args.days) < 1:
        parser.error("all numeric options must be positive")

    key = config_value("RIOT_API_KEY")
    if not key:
        raise RuntimeError("Set RIOT_API_KEY or add it to .env / ../secret/.env")
    client = RiotClient(key)
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    challenger = client.get("https://vn2.api.riotgames.com/tft/league/v1/challenger")
    entries = sorted(challenger.get("entries", []), key=lambda entry: entry.get("leaguePoints", 0), reverse=True)
    players = [entry["puuid"] for entry in entries if entry.get("puuid")][:args.players]
    if not players:
        raise RuntimeError("Challenger endpoint returned no player PUUIDs")
    print(f"Checking {len(players)} Challenger players for matches since {cutoff.date()} UTC", flush=True)

    lists = []
    for number, puuid in enumerate(players, 1):
        url = (f"https://sea.api.riotgames.com/tft/match/v1/matches/by-puuid/"
               f"{quote(puuid, safe='')}/ids?{urlencode({'count': args.matches_per_player})}")
        lists.append(client.get(url))
        if number % 10 == 0:
            print(f"Checked match lists for {number}/{len(players)} players", flush=True)

    db = connect_db(args.db_host)
    try:
        known = existing_ids(db)
        fetched = 0
        checked = 0
        seen = set(known)
        for group in zip_longest(*lists):
            for match_id in group:
                if match_id is None or match_id in seen:
                    continue
                seen.add(match_id)
                url = f"https://sea.api.riotgames.com/tft/match/v1/matches/{quote(match_id, safe='')}"
                match = client.get(url)
                checked += 1
                info = match.get("info", {})
                # Ranked TFT only; other queues and older sets would skew rankings.
                if int(info.get("queue_id", info.get("queueId", 0))) != 1100:
                    continue
                if int(info.get("game_datetime", 0)) < cutoff_ms:
                    continue
                insert_match(db, match_id, match)
                fetched += 1
                if fetched % 25 == 0:
                    print(f"Saved {fetched} ranked matches ({checked} unique matches checked)", flush=True)
                if fetched >= args.max_matches:
                    print(f"Done: saved {fetched} new matches to PostgreSQL", flush=True)
                    return
        print(f"Done: saved {fetched} new matches to PostgreSQL; no more match IDs available", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
