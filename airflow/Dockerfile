FROM apache/airflow:2.10.5-python3.11

USER root
RUN python -m venv /opt/dbt-venv \
    && /opt/dbt-venv/bin/pip install --no-cache-dir dbt-core==1.9.0 dbt-postgres==1.9.0
USER airflow
