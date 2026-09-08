"""
Load layer: lands raw DVF rows into MongoDB as-is.

Why MongoDB for the landing zone?
- The raw DVF export schema drifts slightly across years (columns added /
  renamed), which is a poor fit for a rigid relational table.
- We want to keep the untouched source payload for auditability / replay,
  separate from the cleaned analytical model in PostgreSQL.
- Document-level upserts make the extraction step idempotent: re-running a
  DAG for the same year/department will not create duplicates.
"""
from __future__ import annotations

import logging

import pandas as pd
from pymongo import UpdateOne
from pymongo.collection import Collection

from src.common.db_clients import get_mongo_collection

logger = logging.getLogger(__name__)


def _row_to_document(row: pd.Series) -> dict:
    doc = row.where(pd.notnull(row), None).to_dict()
    # Natural key: a mutation can span several rows (several lots), so we
    # combine the mutation id with the commune and property type to keep
    # each physical lot distinct.
    doc["_natural_key"] = (
        f"{doc.get('id_mutation')}_{doc.get('code_commune')}_{doc.get('type_local')}"
    )
    return doc


def load_dataframe(df: pd.DataFrame, collection: Collection | None = None) -> int:
    """
    Upsert every row of the DataFrame into MongoDB, keyed on a natural key
    derived from the DVF mutation id. Returns the number of documents
    written (inserted + updated).
    """
    if df.empty:
        logger.info("Nothing to load: empty DataFrame")
        return 0

    collection = collection or get_mongo_collection()
    collection.create_index("_natural_key", unique=True)

    operations = [
        UpdateOne(
            {"_natural_key": (doc := _row_to_document(row))["_natural_key"]},
            {"$set": doc},
            upsert=True,
        )
        for _, row in df.iterrows()
    ]

    if not operations:
        return 0

    result = collection.bulk_write(operations, ordered=False)
    written = result.upserted_count + result.modified_count
    logger.info(
        "Mongo load complete: %s upserted, %s modified",
        result.upserted_count,
        result.modified_count,
    )
    return written


if __name__ == "__main__":
    import logging as _logging

    from src.extract.dvf_extractor import extract_all

    _logging.basicConfig(level=_logging.INFO)
    raw_df = extract_all()
    load_dataframe(raw_df)
