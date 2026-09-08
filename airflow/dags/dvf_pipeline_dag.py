"""
Airflow DAG: end-to-end DVF real estate pipeline.

    extract_dvf  ->  load_to_mongo  ->  transform_to_warehouse
                                              |
                                              v
                                   flag_anomalies  ->  train_price_model

Design notes:
- Each task is a thin wrapper around a plain Python function from `src/`,
  so the exact same code can be run locally (`python -m src.extract...`)
  or unit-tested, independently of Airflow.
- XCom is used only to pass small summary dicts between tasks (row counts,
  metrics) - never large DataFrames, which stay in Mongo/Postgres between
  steps.
- Scheduled monthly, matching the cadence at which DVF publishes updates.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

sys.path.append("/opt/airflow")  # make the `src` package importable

default_args = {
    "owner": "remy",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def _extract_task(**context):
    from src.extract.dvf_extractor import extract_all

    df = extract_all()
    # Persist to a shared parquet file rather than pushing the DataFrame
    # through XCom, which is only meant for small metadata.
    path = "/opt/airflow/data/raw_extract.parquet"
    df.to_parquet(path, index=False)
    context["ti"].xcom_push(key="row_count", value=len(df))
    context["ti"].xcom_push(key="extract_path", value=path)


def _load_task(**context):
    import pandas as pd

    from src.load.mongo_loader import load_dataframe

    path = context["ti"].xcom_pull(key="extract_path", task_ids="extract_dvf")
    df = pd.read_parquet(path)
    written = load_dataframe(df)
    context["ti"].xcom_push(key="written_count", value=written)


def _transform_task(**context):
    from src.transform.mongo_to_postgres import run_transform

    stats = run_transform()
    context["ti"].xcom_push(key="transform_stats", value=stats)


def _anomaly_task(**context):
    from src.ml.anomaly_detection import flag_outliers

    flagged = flag_outliers()
    context["ti"].xcom_push(key="flagged_count", value=flagged)


def _train_task(**context):
    from src.ml.train_price_model import train_price_model

    metrics = train_price_model()
    context["ti"].xcom_push(key="model_metrics", value=metrics)


with DAG(
    dag_id="dvf_pipeline",
    description="Extract DVF open data, land it in Mongo, model it into the DWH, train the price model",
    default_args=default_args,
    schedule_interval="@monthly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["dvf", "elt", "ml", "showcase"],
) as dag:

    extract_dvf = PythonOperator(
        task_id="extract_dvf",
        python_callable=_extract_task,
    )

    load_to_mongo = PythonOperator(
        task_id="load_to_mongo",
        python_callable=_load_task,
    )

    transform_to_warehouse = PythonOperator(
        task_id="transform_to_warehouse",
        python_callable=_transform_task,
    )

    flag_anomalies = PythonOperator(
        task_id="flag_anomalies",
        python_callable=_anomaly_task,
    )

    train_price_model = PythonOperator(
        task_id="train_price_model",
        python_callable=_train_task,
    )

    extract_dvf >> load_to_mongo >> transform_to_warehouse >> flag_anomalies >> train_price_model
