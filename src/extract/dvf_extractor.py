"""
Extraction module for the DVF (Demandes de Valeurs Foncieres) open dataset.

Source: https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/departements/{dept}.csv.gz
Published by the French Direction Generale des Finances Publiques (DGFiP)
and packaged by Cerema / Etalab as part of the geo-dvf project.

This module is deliberately I/O-only: it downloads and parses the raw CSV
files into pandas DataFrames. No business transformation happens here -
that is the responsibility of the transform layer, once the raw payload
has been landed in MongoDB.
"""
from __future__ import annotations

import gzip
import io
import logging

import pandas as pd
import requests

from src.common.config import DVF

logger = logging.getLogger(__name__)

# Columns we actually need from the (much wider) raw DVF export.
DVF_COLUMNS = [
    "id_mutation",
    "date_mutation",
    "nature_mutation",
    "valeur_fonciere",
    "code_commune",
    "nom_commune",
    "code_departement",
    "code_type_local",
    "type_local",
    "surface_reelle_bati",
    "nombre_pieces_principales",
    "surface_terrain",
    "longitude",
    "latitude",
]


def _build_url(year: str, department: str) -> str:
    return f"{DVF.base_url}/{year}/departements/{department}.csv.gz"


def download_department_year(year: str, department: str, timeout: int = 60) -> pd.DataFrame:
    """
    Download and parse a single (year, department) DVF extract.

    Returns an empty DataFrame (with a warning logged) if the file does not
    exist for that year/department combination, rather than raising, so a
    single missing file does not abort a larger backfill.
    """
    url = _build_url(year, department)
    logger.info("Downloading DVF extract: %s", url)

    response = requests.get(url, timeout=timeout)
    if response.status_code == 404:
        logger.warning("No DVF file found for year=%s department=%s", year, department)
        return pd.DataFrame(columns=DVF_COLUMNS)
    response.raise_for_status()

    with gzip.open(io.BytesIO(response.content), "rt", encoding="utf-8") as f:
        df = pd.read_csv(f, usecols=lambda c: c in DVF_COLUMNS, low_memory=False)

    df["source_year"] = year
    logger.info(
        "Downloaded %s rows for year=%s department=%s", len(df), year, department
    )
    return df


def extract_all(years: list[str] | None = None, departments: list[str] | None = None) -> pd.DataFrame:
    """
    Extract and concatenate DVF data for every (year, department) pair
    configured via DVF_YEARS / DVF_DEPARTMENTS.
    """
    years = years or DVF.years
    departments = departments or DVF.departments

    frames = []
    for year in years:
        for department in departments:
            frames.append(download_department_year(year, department))

    if not frames:
        return pd.DataFrame(columns=DVF_COLUMNS)

    combined = pd.concat(frames, ignore_index=True)
    logger.info("Extraction complete: %s total raw rows", len(combined))
    return combined


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = extract_all()
    print(data.head())
    print(f"Total rows: {len(data)}")
