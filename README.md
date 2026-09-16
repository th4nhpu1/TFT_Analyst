# TFT Analyst

TFT Analyst collects VN2 Challenger match data from Riot, stores raw match JSON
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
recent match histories for up to 100 VN2 Challenger players and saves up to 1000
new ranked matches from the last 7 days. Existing match IDs are skipped. The
second command refreshes the dbt tables. The Streamlit page refreshes its cached
queries within five minutes.

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
Each player counts once per unit or item on their final board. Average
placement is lower-is-better; top-four rate and appearance count are shown
alongside it. Exact final-board unit combinations form the initial comp table.
These are associations, not estimates of a unit or item's causal effect.

For direct database inspection, start pgAdmin with
`docker compose --env-file ../secret/.env up -d pgadmin` and open
http://localhost:8080.
