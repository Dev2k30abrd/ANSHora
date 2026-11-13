"""
SQLAlchemy Base & Engine configuration for Anshora.
Supports PostgreSQL (production) and SQLite (local dev fallback).
"""
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core import config as cfg


def get_database_url() -> str:
    url = cfg.DATABASE_URL
    if not url:
        return f"sqlite:///{cfg.DB_PATH}"
    # Normalize legacy postgres:// to postgresql+psycopg2://
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


db_url = get_database_url()
is_sqlite = db_url.startswith("sqlite")

engine_kwargs = {"pool_pre_ping": True}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_engine(db_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def generate_uuid() -> str:
    return uuid.uuid4().hex


def utc_now():
    return datetime.now(timezone.utc)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
