"""Guarded helpers for disposable PostgreSQL integration databases."""

from __future__ import annotations

import os
import re
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url


POSTGRES_ADMIN_URL_ENV = "MIGRATION_TEST_POSTGRES_ADMIN_URL"
REQUIRE_POSTGRES_ENV = "LIGHTHOUSE_REQUIRE_POSTGRES_INTEGRATION"
DISPOSABLE_DATABASE_PREFIXES = (
    "lighthouse_migration_",
    "lighthouse_startup_",
)
DATABASE_NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")


def postgres_integration_required() -> bool:
    return os.getenv(REQUIRE_POSTGRES_ENV) == "1"


def postgres_admin_url_or_skip() -> str:
    admin_url = os.getenv(POSTGRES_ADMIN_URL_ENV, "").strip()
    if admin_url:
        validate_postgres_admin_url(admin_url)
        return admin_url

    message = f"Set {POSTGRES_ADMIN_URL_ENV} to run PostgreSQL integration tests"
    if postgres_integration_required():
        pytest.fail(message)
    pytest.skip(message)


def validate_postgres_admin_url(admin_url: str) -> None:
    parsed_url = make_url(admin_url)
    if not parsed_url.drivername.startswith("postgresql"):
        raise ValueError(f"{POSTGRES_ADMIN_URL_ENV} must use a PostgreSQL URL")
    if parsed_url.database and is_disposable_database_name(parsed_url.database):
        raise ValueError(
            f"{POSTGRES_ADMIN_URL_ENV} must not target a disposable test database"
        )
    if parsed_url.database != "postgres":
        raise ValueError(
            f"{POSTGRES_ADMIN_URL_ENV} must target the postgres administrative database"
        )


def is_disposable_database_name(database_name: str) -> bool:
    return DATABASE_NAME_PATTERN.fullmatch(database_name) is not None and any(
        database_name.startswith(prefix) for prefix in DISPOSABLE_DATABASE_PREFIXES
    )


def create_postgres_test_database(admin_url: str, *, prefix: str) -> tuple[Engine, str]:
    validate_postgres_admin_url(admin_url)
    if prefix not in DISPOSABLE_DATABASE_PREFIXES:
        raise ValueError(f"Unsupported PostgreSQL test database prefix: {prefix}")

    parsed_admin_url = make_url(admin_url)
    database_name = f"{prefix}{uuid4().hex}"
    if not is_disposable_database_name(database_name):
        raise RuntimeError("Generated PostgreSQL test database name is not disposable")

    admin_engine = create_engine(parsed_admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    except Exception:
        admin_engine.dispose()
        raise
    database_url = parsed_admin_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    return admin_engine, database_url


def drop_postgres_test_database(admin_engine: Engine, database_url: str) -> None:
    database_name = make_url(database_url).database
    try:
        if database_name is None or not is_disposable_database_name(database_name):
            raise RuntimeError(
                "Refusing to drop a database outside the PostgreSQL test namespaces"
            )

        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
    finally:
        admin_engine.dispose()
