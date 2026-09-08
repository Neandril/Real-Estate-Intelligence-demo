"""
Centralised configuration for the whole pipeline.

All settings are read from environment variables so the exact same code
runs identically on a laptop (.env file) and inside the Airflow / dashboard
containers (variables injected by docker-compose.yml).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load a local .env file if present. In containers, docker-compose already
# provides the environment, so this is a no-op there.
load_dotenv()


def _get_list(env_var: str, default: str) -> list[str]:
    raw = os.getenv(env_var, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class MongoConfig:
    uri: str = field(default_factory=lambda: os.getenv("MONGO_URI", "mongodb://localhost:27017"))
    database: str = field(default_factory=lambda: os.getenv("MONGO_DB", "dvf_raw"))
    collection: str = field(default_factory=lambda: os.getenv("MONGO_COLLECTION", "raw_transactions"))


@dataclass(frozen=True)
class PostgresConfig:
    host: str = field(default_factory=lambda: os.getenv("POSTGRES_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("POSTGRES_PORT", "5433")))
    database: str = field(default_factory=lambda: os.getenv("POSTGRES_DB", "dvf_dwh"))
    user: str = field(default_factory=lambda: os.getenv("POSTGRES_USER", "dvf_user"))
    password: str = field(default_factory=lambda: os.getenv("POSTGRES_PASSWORD", "dvf_password"))

    @property
    def sqlalchemy_uri(self) -> str:
        return (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


@dataclass(frozen=True)
class DVFConfig:
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "DVF_BASE_URL", "https://files.data.gouv.fr/geo-dvf/latest/csv"
        )
    )
    years: list[str] = field(default_factory=lambda: _get_list("DVF_YEARS", "2023,2024"))
    departments: list[str] = field(default_factory=lambda: _get_list("DVF_DEPARTMENTS", "29,75"))


@dataclass(frozen=True)
class MLConfig:
    model_path: str = field(
        default_factory=lambda: os.getenv("MODEL_PATH", "./models/price_model.joblib")
    )
    test_size: float = 0.2
    random_state: int = 42
    # Simple, explainable feature set on purpose: this is a showcase project,
    # the goal is a clear, defensible modelling story rather than raw accuracy.
    numeric_features: tuple[str, ...] = ("surface_real_bati", "surface_terrain", "nb_rooms")
    categorical_features: tuple[str, ...] = ("department_code", "property_type_code")
    target: str = "sale_price"


MONGO = MongoConfig()
POSTGRES = PostgresConfig()
DVF = DVFConfig()
ML = MLConfig()
