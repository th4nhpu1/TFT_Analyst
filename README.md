# TFT Analyst

TFT Analyst collects VN2 Gold-through-Challenger match data from Riot, stores raw match JSON
in PostgreSQL, builds ratings with dbt, and shows them in Streamlit. Airflow can
remove matches older than one week, then run ingest and dbt nightly.

## Start the database and dashboard

Keep `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`PGADMIN_DEFAULT_EMAIL`, `PGADMIN_DEFAULT_PASSWORD`, and `RIOT_API_KEY` in
`../secret/.env`. From this directory:

```powershell
docker compose --env-file ../secret/.env up -d --build server
```

This starts PostgreSQL, runs dbt, then starts the dashboard at
http://localhost:8501. The raw matches stay in `public.matches`; dbt tables are
created in the `analytics` schema. No CSV is used.

On a new database, run the manual refresh below once to populate the dashboard.

## Refresh matches manually

```powershell
docker compose --env-file ../secret/.env --profile manual run --rm ingest
docker compose --env-file ../secret/.env run --rm dbt
```

The first command runs `extract/loadData.py` against PostgreSQL. It checks
20 recent match IDs for 50 randomly sampled players in each of Gold, Platinum,
Emerald, Diamond, Master, Grandmaster, and Challenger (350 players, up to 7,000
references before deduplication). It keeps ranked matches from the last 7 days.
Existing match IDs are skipped. The
second command refreshes the dbt tables. The Streamlit page refreshes its cached
queries within five minutes.

Gold through Diamond sample from randomized pages across divisions I–IV, then
randomly select 50 unique players from that pool. Master through Challenger
sample from the full returned tier roster. This is a random page-pool sample,
not a guaranteed uniform sample of every player in the region. If a tier has
fewer than 50 eligible players, collection reports the shortfall instead of
silently substituting players from another rank.

Riot rate limits mean a full collection can take hours. PostgreSQL's
`ingestion_runs` table stores the sampled roster, its current rank, match
histories, and progress. Repeating the collector resumes an unfinished run;
`--new-sample` explicitly starts a fresh one. Completed runs use a fresh sample
next time. A database lock prevents two collectors running simultaneously.
Some players have fewer than 20 matches, and old or non-ranked matches are
excluded. Source rank describes the sampled player now, not every opponent's
rank at the time of the match.

## Schedule nightly refreshes

```powershell
docker compose --env-file ../secret/.env --profile scheduler up -d --build airflow
```

The `tft_nightly_refresh` Airflow DAG removes raw matches played more than 7 days
ago, runs ingestion, then rebuilds dbt tables at 02:00 Vietnam time
each day. The local Airflow UI is at http://localhost:8081. This uses Airflow's
standalone mode for local development; keep Docker running for the schedule to
run. The dbt rebuild still runs if Riot ingestion fails, so removed matches are
excluded from the dashboard. Riot development keys expire regularly, so a stable
personal key is needed for unattended nightly refreshes.

## How the ratings work

The dashboard uses the latest 7 days of ranked matches, separated by TFT set.
Click a champion, item, comp name, or its **See more** button to open details.
Champion details rank items equipped on that champion; item details rank their
champion holders. Both require at least **10 distinct matches** per pair and
sort by best (lowest) average placement. Duplicate copies of an item or champion
count once per player result for a pairing. The displayed match count is
distinct lobbies; average placement and top-four rate use player results.
Each player counts once per unit or item on their final board. Average
placement is lower-is-better; top-four rate and appearance count are shown
alongside it. Comps group by the two most itemized distinct champions, the
highest active silver-or-better trait, and a reroll flag when at least two
board units have three or more stars. Item count wins first (capped at three),
then star level, then champion ID. The chosen pair is alphabetized so swapping
which carry has more items does not split the comp. Champion forms share a name.

Current Riot match trait styles are treated as silver (2), gold (4), and
prismatic (5). Unique (3), inactive, bronze, and unknown styles do not qualify;
without a qualifying trait the label is `flex`. Tied traits favor more active
units, then higher achieved tier, then trait ID.

Each comp saves its most frequent champion lineup in PostgreSQL, including
duplicate champions but ignoring stars and items when counting that lineup.
Ties favor better average placement, then alphabetical lineup order. The table
also saves its frequency and the latest actual board example with stars/items
and source match. In Streamlit, choose a comp below the ratings to inspect it.
Empty boards are excluded because they cannot be named by champions.
These are associations, not estimates of a unit or item's causal effect.

For direct database inspection, start pgAdmin with
`docker compose --env-file ../secret/.env up -d pgadmin` and open
http://localhost:8080.
