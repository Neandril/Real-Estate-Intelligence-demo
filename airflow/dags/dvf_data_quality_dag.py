"""
Airflow DAG: lightweight data quality checks over the warehouse.

Runs daily, independently of the monthly ingestion DAG, and fails loudly
(via AirflowFailException) if a check does not pass - the kind of guardrail
a client would expect around a production pipeline, kept intentionally
small here for readability.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.operators.python import PythonOperator

sys.path.append("/opt/airflow")

default_args = {"owner": "remy", "retries": 1, "retry_delay": timedelta(minutes=5)}


def _check_no_negative_prices(**_):
    from sqlalchemy import text

    from src.common.db_clients import get_postgres_engine

    engine = get_postgres_engine()
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM dwh.fact_transactions WHERE sale_price <= 0")
        ).scalar_one()
    if count > 0:
        raise AirflowFailException(f"{count} transactions with a non-positive sale price")


def _check_fact_row_count_growth(**_):
    from sqlalchemy import text

    from src.common.db_clients import get_postgres_engine

    engine = get_postgres_engine()
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM dwh.fact_transactions")).scalar_one()
    if count == 0:
        raise AirflowFailException("fact_transactions is empty - has the ELT DAG run yet?")


def _check_orphan_dimension_keys(**_):
    from sqlalchemy import text

    from src.common.db_clients import get_postgres_engine

    engine = get_postgres_engine()
    with engine.connect() as conn:
        orphans = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM dwh.fact_transactions f
                LEFT JOIN dwh.dim_commune c ON c.commune_key = f.commune_key
                WHERE c.commune_key IS NULL
                """
            )
        ).scalar_one()
    if orphans > 0:
        raise AirflowFailException(f"{orphans} fact rows reference a missing commune dimension row")


with DAG(
    dag_id="dvf_data_quality",
    description="Daily data quality checks on the DVF analytical warehouse",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["dvf", "data-quality"],
) as dag:

    PythonOperator(task_id="check_no_negative_prices", python_callable=_check_no_negative_prices)
    PythonOperator(task_id="check_fact_row_count", python_callable=_check_fact_row_count_growth)
    PythonOperator(task_id="check_orphan_keys", python_callable=_check_orphan_dimension_keys)
