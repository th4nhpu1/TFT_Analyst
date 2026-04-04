import os
import time
import requests
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json

# Load .env
load_dotenv()

RIOT_API_KEY = os.getenv("RIOT_API_KEY")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")

HEADERS = {
    "X-Riot-Token": RIOT_API_KEY
}

platform = "vn2"
region = "sea"

def make_request(url):
    while True:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            print("Rate limit exceeded. Retrying in 2 minutes...")
            time.sleep(120)
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return None

def connect_db():
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )
    return conn

def create_tables(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            match_id VARCHAR(30) PRIMARY KEY,
            match_data JSONB
        );
    """)
    conn.commit()
    return cur

def load_top_players(conn, cur):
    url = f"https://{platform}.api.riotgames.com/tft/league/v1/challenger"
    data = make_request(url)
    puuid_list = []
    if data and "entries" in data:
        for entry in data["entries"]:
            puuid_list.append(entry["puuid"])
            print(f"Added player with PUUID {entry['puuid']} to the list.")
    return puuid_list

def load_matches(conn, cur, puuid_list):
    for puuid in puuid_list:
        url = f"https://{region}.api.riotgames.com/tft/match/v1/matches/by-puuid/{puuid}/ids?count=30"
        match_ids = make_request(url)
        if match_ids:
            for match_id in match_ids:
                match_url = f"https://{region}.api.riotgames.com/tft/match/v1/matches/{match_id}"
                match_data = make_request(match_url)
                if match_data:
                    cur.execute("""
                        INSERT INTO matches (match_id, match_data)
                        VALUES (%s, %s)
                        ON CONFLICT (match_id) DO NOTHING;
                    """, (match_id, Json(match_data)))
                    conn.commit()
                    print(f"Inserted match {match_id} into database.")
                else:
                    print(f"Failed to fetch data for match {match_id}. Skipping.")
        else:
            print(f"Failed to fetch match IDs for player {puuid}. Skipping.")

if __name__ == "__main__":
    conn = connect_db()
    cur = create_tables(conn)
    puuid_list = load_top_players(conn, cur)
    load_matches(conn, cur, puuid_list)
    cur.close()
    conn.close()



