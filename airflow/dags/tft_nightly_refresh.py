"""Nightly retention, Riot ingestion, and dbt ratings in PostgreSQL."""

from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator


with DAG(
    dag_id="tft_nightly_refresh",
    description="Remove old matches, fetch recent matches, and rebuild ratings",
    start_date=pendulum.datetime(2026, 9, 16, tz="Asia/Ho_Chi_Minh"),
    schedule="0 2 * * *",
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=10)},
    tags=["tft"],
) as dag:
    prune = BashOperator(
        task_id="remove_old_matches",
        bash_command="python /opt/airflow/project/extract/pruneMatches.py --days 7 --db-host db",
    )
    ingest = BashOperator(
        task_id="ingest_matches",
        bash_command="python /opt/airflow/project/extract/loadData.py --max-matches 200 --days 7 --db-host db",
    )
    ratings = BashOperator(
        task_id="build_ratings",
        trigger_rule="all_done",
        bash_command=(
            "/opt/dbt-venv/bin/dbt run --project-dir /opt/airflow/project/dbt "
            "--profiles-dir /opt/airflow/project/dbt"
        ),
    )
    prune >> ingest >> ratings
