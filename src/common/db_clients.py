"""
Factory functions for database clients (MongoDB and PostgreSQL).

Keeping connection creation in one place makes it trivial to swap
implementations (e.g. connection pooling, retries) without touching the
rest of the codebase.
"""
from __future__ import annotations

import logging

from pymongo import MongoClient
from pymongo.collection import Collection
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.common.config import MONGO, POSTGRES

logger = logging.getLogger(__name__)


def get_mongo_collection() -> Collection:
    """Return the MongoDB collection used as the raw landing zone."""
    client = MongoClient(MONGO.uri, serverSelectionTimeoutMS=5000)
    db = client[MONGO.database]
    logger.info("Connected to MongoDB database '%s'", MONGO.database)
    return db[MONGO.collection]


def get_postgres_engine() -> Engine:
    """Return a SQLAlchemy engine for the analytical warehouse."""
    engine = create_engine(POSTGRES.sqlalchemy_uri, pool_pre_ping=True)
    logger.info("Created PostgreSQL engine for '%s'", POSTGRES.database)
    return engine
