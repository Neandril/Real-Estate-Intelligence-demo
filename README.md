# DVF Real Estate Intelligence Platform

An end-to-end data engineering showcase project built around the French
**DVF open dataset** (real estate transactions published by the DGFiP /
Cerema on data.gouv.fr).

It demonstrates a complete, production-shaped pipeline in a single
`docker compose up`: a NoSQL landing zone, an orchestrated ELT process, an
analytical star schema, two machine learning components, and an
interactive dashboard.

## Stack

| Layer            | Technology |
|-------------------|------------|
| Raw landing zone  | MongoDB |
| Orchestration      | Apache Airflow |
| Analytical warehouse | PostgreSQL (star schema) |
| Machine learning     | scikit-learn (price prediction + anomaly detection) |
| Presentation           | Streamlit (KPIs, interactive map, live price estimator) |
| Packaging               | Docker Compose |

See [`docs/architecture.md`](docs/architecture.md) for the full data flow
diagram and design rationale.

## Project structure

```
.
├── airflow/                 # Airflow image + DAGs
│   └── dags/
│       ├── dvf_pipeline_dag.py        # extract -> load -> transform -> ML
│       └── dvf_data_quality_dag.py    # daily warehouse guardrail checks
├── dashboard/                # Streamlit application
├── src/
│   ├── extract/               # DVF download & parsing
│   ├── load/                  # MongoDB landing zone loader
│   ├── transform/              # ELT: Mongo -> PostgreSQL star schema
│   ├── ml/                      # Price prediction + anomaly detection
│   └── common/                   # Shared config & DB clients
├── sql/schema.sql                 # Star schema DDL (auto-applied on first boot)
├── tests/                          # Unit tests (pytest)
├── docker-compose.yml
└── requirements.txt
```

## Getting started

### 1. Configure

```bash
cp .env.example .env
# adjust DVF_YEARS / DVF_DEPARTMENTS if you want a different scope
```

### 2. Start the stack

```bash
docker compose up -d --build
```

This starts:
- MongoDB on `localhost:27017` (+ Mongo Express UI on `:8081`)
- PostgreSQL warehouse on `localhost:5433` (schema auto-created)
- Airflow webserver on `localhost:8080` (login: `admin` / `admin`)
- Streamlit dashboard on `localhost:8501`

### 3. Run the pipeline

In the Airflow UI (`localhost:8080`), unpause and trigger the `dvf_pipeline`
DAG. It will:
1. Download DVF CSV extracts for the configured years/departments
2. Land the raw rows in MongoDB
3. Clean and load them into the PostgreSQL star schema
4. Flag statistical outliers per local market segment
5. Train the price prediction model and persist it to `models/`

The `dvf_data_quality` DAG runs independently and validates warehouse
integrity (no negative prices, no orphan dimension keys, etc.).

### 4. Explore the dashboard

Open `http://localhost:8501` once the pipeline has run once. Three tabs:
- **Overview** — KPIs and price trends
- **Map** — commune-level median price per sqm on an interactive map
- **Price estimator** — live prediction from the trained model

## Running components individually (without Docker)

```bash
pip install -r requirements.txt
python -m src.extract.dvf_extractor      # sanity-check the extraction
python -m src.load.mongo_loader          # extract + load to Mongo
python -m src.transform.mongo_to_postgres # ELT into the warehouse
python -m src.ml.anomaly_detection        # flag outliers
python -m src.ml.train_price_model         # train the price model
streamlit run dashboard/app.py
```

## Tests

```bash
pytest tests/
```

## Data source & licensing

DVF data is published under the [Open Licence 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence)
by the French administration via [data.gouv.fr](https://www.data.gouv.fr/)
and packaged as ready-to-use CSV files by the
[geo-dvf project](https://github.com/cerema/geo-dvf) (Cerema / Etalab).

## About

Built as a portfolio project to demonstrate a full data engineering scope:
NoSQL ingestion, ELT orchestration, dimensional modelling, applied machine
learning, and a client-facing presentation layer — the kind of end-to-end
delivery available for freelance missions.
