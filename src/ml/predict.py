"""
Thin inference wrapper around the persisted price-prediction pipeline.
Used by the Streamlit dashboard to turn a form submission into a prediction.
"""
from __future__ import annotations

import functools
import logging

import joblib
import pandas as pd

from src.common.config import ML

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _load_model():
    logger.info("Loading model from %s", ML.model_path)
    return joblib.load(ML.model_path)


def predict_price(
    surface_real_bati: float,
    surface_terrain: float,
    nb_rooms: int,
    department_code: str,
    property_type_code: str,
) -> float:
    """Return an estimated sale price (EUR) for a single property."""
    model = _load_model()
    row = pd.DataFrame(
        [
            {
                "surface_real_bati": surface_real_bati,
                "surface_terrain": surface_terrain,
                "nb_rooms": nb_rooms,
                "department_code": department_code,
                "property_type_code": property_type_code,
            }
        ]
    )
    prediction = model.predict(row)[0]
    return float(prediction)
