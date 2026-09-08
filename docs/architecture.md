# Architecture

## Data flow

```
                     DVF open dataset (data.gouv.fr / Cerema)
                                    |
                                    v
                     +---------------------------+
                     |   Extract (requests +     |
                     |   pandas) - src/extract    |
                     +---------------------------+
                                    |
                                    v
                     +---------------------------+
                     |   Load: MongoDB            |   <-- raw landing zone,
                     |   raw_transactions          |       heterogeneous schema,
                     +---------------------------+       full audit trail
                                    |
                                    v
                     +---------------------------+
                     |   Transform (ELT):         |
                     |   clean, conform, model     |   src/transform
                     +---------------------------+
                                    |
                                    v
                     +---------------------------+
                     |   PostgreSQL star schema    |
                     |   dim_commune, dim_date,    |
                     |   dim_property_type,        |
                     |   fact_transactions          |
                     +---------------------------+
                          |                  |
                          v                  v
              +-------------------+  +----------------------+
              | Anomaly detection |  | Price prediction model|
              | (IsolationForest) |  | (RandomForestRegressor)|
              | src/ml            |  | src/ml                 |
              +-------------------+  +----------------------+
                          |                  |
                          +--------+---------+
                                   v
                     +---------------------------+
                     |   Streamlit dashboard       |
                     |   Overview / Map / Estimator |
                     +---------------------------+
```

All of the above is orchestrated by two Airflow DAGs:

- `dvf_pipeline` (monthly): extract -> load -> transform -> flag anomalies -> train model
- `dvf_data_quality` (daily): guardrail checks against the warehouse

## Why these technology choices

| Concern                | Choice          | Rationale |
|-------------------------|-----------------|-----------|
| Raw landing zone        | MongoDB         | Source schema drifts across years; document upserts make ingestion idempotent |
| Analytical storage      | PostgreSQL       | Star schema is the right shape for BI-style querying and dashboarding |
| Orchestration            | Airflow          | Industry-standard scheduler, explicit DAG dependencies, built-in retries/backfill |
| Modelling                 | scikit-learn      | RandomForest gives a robust, explainable baseline without heavy tuning |
| Presentation              | Streamlit         | Fast to build an interactive, map-based showcase without a separate frontend stack |
| Packaging                  | Docker Compose     | One command spins up the entire stack for a live client demo |

## Extending this project

- Swap the RandomForest for a gradient boosting model (XGBoost/LightGBM) and
  compare via the same `train_and_evaluate` harness.
- Add a `dbt` layer between PostgreSQL raw tables and the star schema for
  more advanced transformation testing/versioning.
- Replace the batch MongoDB landing zone with a streaming ingestion
  (Kafka / Debezium) if the use case required near-real-time updates.
- Add authentication and a proper `AIRFLOW__CORE__FERNET_KEY` before any
  non-local deployment.
