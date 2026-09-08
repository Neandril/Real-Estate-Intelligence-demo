"""
Transform layer of the ELT pipeline.

Reads raw documents from MongoDB, cleans / conforms them, and loads the
result into the PostgreSQL star schema (dwh.dim_commune, dwh.dim_date,
dwh.dim_property_type, dwh.fact_transactions).

This is intentionally "ELT" rather than "ETL": the raw, untransformed
payload is already sitting in MongoDB (the Load step happened first); this
module performs the Transform step against data that is already at rest.
"""
from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.common.db_clients import get_mongo_collection, get_postgres_engine

logger = logging.getLogger(__name__)

VALID_PROPERTY_TYPES = {"1", "2", "3", "4"}


def read_raw_from_mongo() -> pd.DataFrame:
    collection = get_mongo_collection()
    cursor = collection.find({}, {"_id": 0})
    df = pd.DataFrame(list(cursor))
    logger.info("Read %s raw documents from MongoDB", len(df))
    return df


def clean_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply the business rules that turn a raw DVF export into analysis-ready
    transactions:
      - drop rows without a usable price, commune or property type
      - keep only actual sales ("Vente"), not donations/exchanges
      - coerce numeric types and derive price per square metre
      - drop rows with an obviously invalid built surface (<= 0)
    """
    if df.empty:
        return df

    df = df.copy()
    df["type_local"] = (
        pd.to_numeric(df["code_type_local"], errors="coerce")
        .astype("Int64")
        .astype(str)
    )

    df["code_commune"] = (
        pd.to_numeric(df["code_commune"], errors="coerce")
        .astype("Int64")
        .astype(str)
        .str.zfill(5)
    )

    df = df[
        df["nature_mutation"].eq("Vente")
        & df["valeur_fonciere"].notna()
        & df["code_commune"].notna()
        & df["type_local"].isin(VALID_PROPERTY_TYPES)
    ]

    df["valeur_fonciere"] = pd.to_numeric(df["valeur_fonciere"], errors="coerce")
    df["surface_reelle_bati"] = pd.to_numeric(df["surface_reelle_bati"], errors="coerce")
    df["surface_terrain"] = pd.to_numeric(df["surface_terrain"], errors="coerce")
    df["nombre_pieces_principales"] = pd.to_numeric(
        df["nombre_pieces_principales"], errors="coerce"
    )
    df["date_mutation"] = pd.to_datetime(df["date_mutation"], errors="coerce")

    df = df[df["valeur_fonciere"] > 0]
    df = df[(df["surface_reelle_bati"].isna()) | (df["surface_reelle_bati"] > 0)]
    df = df.dropna(subset=["date_mutation"])

    df["price_per_sqm"] = (df["valeur_fonciere"] / df["surface_reelle_bati"]).where(
        df["surface_reelle_bati"] > 0
    )

    logger.info("Cleaned dataset: %s valid transactions", len(df))
    return df


def _upsert_dim_commune(engine: Engine, df: pd.DataFrame) -> None:
    communes = (
        df[["code_commune", "nom_commune", "code_departement", "latitude", "longitude"]]
        .drop_duplicates(subset=["code_commune"])
        .rename(
            columns={
                "code_commune": "insee_code",
                "nom_commune": "commune_name",
                "code_departement": "department_code",
            }
        )
    )
    with engine.begin() as conn:
        for row in communes.itertuples(index=False):
            conn.execute(
                text(
                    """
                    INSERT INTO dwh.dim_commune
                        (insee_code, commune_name, department_code, latitude, longitude)
                    VALUES (:insee_code, :commune_name, :department_code, :latitude, :longitude)
                    ON CONFLICT (insee_code) DO UPDATE SET
                        commune_name = EXCLUDED.commune_name,
                        department_code = EXCLUDED.department_code,
                        latitude = COALESCE(EXCLUDED.latitude, dwh.dim_commune.latitude),
                        longitude = COALESCE(EXCLUDED.longitude, dwh.dim_commune.longitude)
                    """
                ),
                row._asdict(),
            )
    logger.info("Upserted %s communes into dim_commune", len(communes))


def _upsert_dim_date(engine: Engine, df: pd.DataFrame) -> None:
    dates = df["date_mutation"].dropna().dt.normalize().drop_duplicates()
    with engine.begin() as conn:
        for d in dates:
            date_key = int(d.strftime("%Y%m%d"))
            conn.execute(
                text(
                    """
                    INSERT INTO dwh.dim_date
                        (date_key, full_date, year, quarter, month, month_name, day_of_week)
                    VALUES (:date_key, :full_date, :year, :quarter, :month, :month_name, :dow)
                    ON CONFLICT (date_key) DO NOTHING
                    """
                ),
                {
                    "date_key": date_key,
                    "full_date": d.date(),
                    "year": d.year,
                    "quarter": (d.month - 1) // 3 + 1,
                    "month": d.month,
                    "month_name": d.strftime("%B"),
                    "dow": d.dayofweek,
                },
            )
    logger.info("Upserted %s dates into dim_date", len(dates))


def _load_fact_transactions(engine: Engine, df: pd.DataFrame) -> int:
    payload = df.copy()
    payload["date_key"] = payload["date_mutation"].dt.strftime("%Y%m%d").astype(int)

    inserted = 0
    with engine.begin() as conn:
        commune_map = dict(
            conn.execute(text("SELECT insee_code, commune_key FROM dwh.dim_commune")).all()
        )
        property_type_map = dict(
            conn.execute(
                text("SELECT property_type_code, property_type_key FROM dwh.dim_property_type")
            ).all()
        )

        for row in payload.itertuples(index=False):
            commune_key = commune_map.get(row.code_commune)
            property_type_key = property_type_map.get(row.type_local)
            if commune_key is None or property_type_key is None:
                continue

            conn.execute(
                text(
                    """
                    INSERT INTO dwh.fact_transactions
                        (source_id, commune_key, property_type_key, date_key, sale_price,
                         surface_real_bati, surface_terrain, nb_rooms, price_per_sqm)
                    VALUES
                        (:source_id, :commune_key, :property_type_key, :date_key, :sale_price,
                         :surface_real_bati, :surface_terrain, :nb_rooms, :price_per_sqm)
                    ON CONFLICT (source_id, commune_key, property_type_key) DO UPDATE SET
                        sale_price = EXCLUDED.sale_price,
                        surface_real_bati = EXCLUDED.surface_real_bati,
                        surface_terrain = EXCLUDED.surface_terrain,
                        nb_rooms = EXCLUDED.nb_rooms,
                        price_per_sqm = EXCLUDED.price_per_sqm
                    """
                ),
                {
                    "source_id": str(row.id_mutation),
                    "commune_key": commune_key,
                    "property_type_key": property_type_key,
                    "date_key": row.date_key,
                    "sale_price": float(row.valeur_fonciere),
                    "surface_real_bati": _nan_to_none(row.surface_reelle_bati),
                    "surface_terrain": _nan_to_none(row.surface_terrain),
                    "nb_rooms": _nan_to_none(row.nombre_pieces_principales),
                    "price_per_sqm": _nan_to_none(row.price_per_sqm),
                },
            )
            inserted += 1

    logger.info("Loaded %s rows into fact_transactions", inserted)
    return inserted


def _nan_to_none(value):
    return None if pd.isna(value) else value


def run_transform() -> dict:
    """Full ELT transform step: Mongo -> clean -> PostgreSQL star schema."""
    engine = get_postgres_engine()

    raw_df = read_raw_from_mongo()
    clean_df = clean_transactions(raw_df)

    if clean_df.empty:
        logger.warning("No clean transactions to load - skipping warehouse load")
        return {"raw_rows": len(raw_df), "clean_rows": 0, "loaded_rows": 0}

    _upsert_dim_commune(engine, clean_df)
    _upsert_dim_date(engine, clean_df)
    loaded = _load_fact_transactions(engine, clean_df)

    return {"raw_rows": len(raw_df), "clean_rows": len(clean_df), "loaded_rows": loaded}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stats = run_transform()
    print(stats)
