"""
Unsupervised anomaly detection over the warehouse's price-per-sqm
distribution, grouped by (department, property type).

Flags transactions whose price per square metre is a strong statistical
outlier within its own local market segment - useful to catch data entry
errors in the source file (e.g. a missing digit) as well as genuinely
unusual sales. Flagged rows are excluded from the training set used by
train_price_model.py so the regressor is not skewed by bad data.

Method: IsolationForest per (department_code, property_type_code) segment.
A per-segment model is deliberately used instead of one global model,
since "expensive" in Paris and "expensive" in a rural commune are not
comparable on an absolute scale.
"""
from __future__ import annotations

import logging

import pandas as pd
from sklearn.ensemble import IsolationForest
from sqlalchemy import text

from src.common.config import ML
from src.common.db_clients import get_postgres_engine

logger = logging.getLogger(__name__)

MIN_SEGMENT_SIZE = 30
CONTAMINATION = 0.02  # expected proportion of outliers per segment


def _fetch_segmented_data() -> pd.DataFrame:
    engine = get_postgres_engine()
    query = """
        SELECT
            f.transaction_key,
            f.price_per_sqm,
            c.department_code,
            pt.property_type_code
        FROM dwh.fact_transactions f
        JOIN dwh.dim_commune c ON c.commune_key = f.commune_key
        JOIN dwh.dim_property_type pt ON pt.property_type_key = f.property_type_key
        WHERE f.price_per_sqm IS NOT NULL
    """
    return pd.read_sql(query, engine)


def flag_outliers() -> int:
    df = _fetch_segmented_data()
    if df.empty:
        logger.warning("No rows with price_per_sqm available - skipping anomaly detection")
        return 0

    outlier_keys: list[int] = []

    for (dept, ptype), segment in df.groupby(["department_code", "property_type_code"]):
        if len(segment) < MIN_SEGMENT_SIZE:
            # Too few points for a meaningful model: skip rather than guess.
            continue

        model = IsolationForest(
            contamination=CONTAMINATION, random_state=ML.random_state, n_jobs=-1
        )
        segment = segment.copy()
        segment["flag"] = model.fit_predict(segment[["price_per_sqm"]])
        outliers = segment.loc[segment["flag"] == -1, "transaction_key"].tolist()
        outlier_keys.extend(outliers)
        logger.info(
            "Segment dept=%s type=%s: %s/%s flagged as outliers",
            dept,
            ptype,
            len(outliers),
            len(segment),
        )

    if outlier_keys:
        engine = get_postgres_engine()
        with engine.begin() as conn:
            conn.execute(text("UPDATE dwh.fact_transactions SET is_outlier = FALSE"))
            conn.execute(
                text(
                    "UPDATE dwh.fact_transactions SET is_outlier = TRUE "
                    "WHERE transaction_key = ANY(:keys)"
                ),
                {"keys": outlier_keys},
            )
    logger.info("Flagged %s transactions as outliers in total", len(outlier_keys))
    return len(outlier_keys)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = flag_outliers()
    print(f"Flagged {count} outliers")
