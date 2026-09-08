"""
Trains a price-prediction model on top of the analytical warehouse.

Model choice: a RandomForestRegressor is used deliberately over something
fancier - for a showcase project the priority is a robust, easily explained
baseline (feature importances, no scaling required, handles non-linearities)
rather than squeezing out marginal accuracy gains.

The trained pipeline (preprocessing + model) is persisted as a single
joblib artifact so the dashboard can load and call it directly.
"""
from __future__ import annotations

import logging

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from pathlib import Path

from src.common.config import ML
from src.common.db_clients import get_postgres_engine

logger = logging.getLogger(__name__)

TRAINING_QUERY = """
    SELECT
        f.sale_price,
        f.surface_real_bati,
        f.surface_terrain,
        f.nb_rooms,
        c.department_code,
        pt.property_type_code
    FROM dwh.fact_transactions f
    JOIN dwh.dim_commune c ON c.commune_key = f.commune_key
    JOIN dwh.dim_property_type pt ON pt.property_type_key = f.property_type_key
    WHERE f.sale_price BETWEEN 5000 AND 3000000
      AND f.surface_real_bati IS NOT NULL
      AND f.is_outlier IS NOT TRUE
"""


def load_training_data() -> pd.DataFrame:
    engine = get_postgres_engine()
    df = pd.read_sql(TRAINING_QUERY, engine)
    df = df.dropna(subset=[ML.target, *ML.numeric_features])
    logger.info("Loaded %s training rows from the warehouse", len(df))
    return df


def build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", "passthrough", list(ML.numeric_features)),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                list(ML.categorical_features),
            ),
        ]
    )
    model = RandomForestRegressor(
        n_estimators=300,
        max_depth=18,
        min_samples_leaf=3,
        n_jobs=-1,
        random_state=ML.random_state,
    )
    return Pipeline(steps=[("preprocess", preprocessor), ("model", model)])


def train_and_evaluate(df: pd.DataFrame) -> tuple[Pipeline, dict]:
    features = list(ML.numeric_features) + list(ML.categorical_features)
    X = df[features]
    y = df[ML.target]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=ML.test_size, random_state=ML.random_state
    )

    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    predictions = pipeline.predict(X_test)
    metrics = {
        "mae": mean_absolute_error(y_test, predictions),
        "mape": mean_absolute_percentage_error(y_test, predictions),
        "r2": r2_score(y_test, predictions),
        "n_train": len(X_train),
        "n_test": len(X_test),
    }
    logger.info("Model evaluation: %s", metrics)
    return pipeline, metrics


def train_price_model() -> dict:
    df = load_training_data()
    if len(df) < 50:
        raise RuntimeError(
            f"Not enough training data ({len(df)} rows) - run the ELT pipeline first."
        )

    pipeline, metrics = train_and_evaluate(df)

    Path(ML.model_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, ML.model_path)

    logger.info("Saved trained model to %s", ML.model_path)
    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = train_price_model()
    print(result)
