"""
Unit tests for the cleaning logic in src/transform/mongo_to_postgres.py.

These run against in-memory DataFrames only - no database required - so
they are fast and safe to run in any CI environment.
"""
import pandas as pd
import pytest

from src.transform.mongo_to_postgres import clean_transactions


@pytest.fixture
def raw_sample() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # Valid sale
            {
                "id_mutation": "1",
                "nature_mutation": "Vente",
                "valeur_fonciere": 200000,
                "code_commune": "29001",
                "nom_commune": "Argol",
                "code_departement": "29",
                "type_local": "1",
                "surface_reelle_bati": 90,
                "surface_terrain": 500,
                "nombre_pieces_principales": 4,
                "date_mutation": "2023-05-10",
                "latitude": 48.2,
                "longitude": -4.3,
            },
            # Not a sale -> should be dropped
            {
                "id_mutation": "2",
                "nature_mutation": "Donation",
                "valeur_fonciere": 150000,
                "code_commune": "29001",
                "nom_commune": "Argol",
                "code_departement": "29",
                "type_local": "1",
                "surface_reelle_bati": 80,
                "surface_terrain": 400,
                "nombre_pieces_principales": 3,
                "date_mutation": "2023-06-01",
                "latitude": 48.2,
                "longitude": -4.3,
            },
            # Missing price -> should be dropped
            {
                "id_mutation": "3",
                "nature_mutation": "Vente",
                "valeur_fonciere": None,
                "code_commune": "29001",
                "nom_commune": "Argol",
                "code_departement": "29",
                "type_local": "2",
                "surface_reelle_bati": 45,
                "surface_terrain": None,
                "nombre_pieces_principales": 2,
                "date_mutation": "2023-07-15",
                "latitude": 48.2,
                "longitude": -4.3,
            },
            # Invalid property type code -> should be dropped
            {
                "id_mutation": "4",
                "nature_mutation": "Vente",
                "valeur_fonciere": 90000,
                "code_commune": "29001",
                "nom_commune": "Argol",
                "code_departement": "29",
                "type_local": "9",
                "surface_reelle_bati": 30,
                "surface_terrain": None,
                "nombre_pieces_principales": 1,
                "date_mutation": "2023-08-20",
                "latitude": 48.2,
                "longitude": -4.3,
            },
        ]
    )


def test_clean_transactions_keeps_only_valid_sales(raw_sample):
    result = clean_transactions(raw_sample)
    assert len(result) == 1
    assert result.iloc[0]["id_mutation"] == "1"


def test_clean_transactions_computes_price_per_sqm(raw_sample):
    result = clean_transactions(raw_sample)
    expected = 200000 / 90
    assert result.iloc[0]["price_per_sqm"] == pytest.approx(expected)


def test_clean_transactions_handles_empty_dataframe():
    empty = pd.DataFrame()
    result = clean_transactions(empty)
    assert result.empty
