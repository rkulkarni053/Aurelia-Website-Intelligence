"""Lightweight schema upgrades for dev DBs (no Alembic)."""

from __future__ import annotations

import uuid

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_company_schema(engine: Engine) -> None:
    """Create companies table and link existing projects if needed."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())

    if "companies" not in tables:
        # create_all in lifespan will add it; column backfill runs after.
        return

    cols = {c["name"] for c in insp.get_columns("projects")}
    if "company_id" in cols:
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE projects "
                "ADD COLUMN company_id UUID REFERENCES companies(id) ON DELETE SET NULL"
            )
        )
        default_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO companies (id, name, description, created_at) "
                "VALUES (:id, :name, NULL, NOW())"
            ),
            {"id": str(default_id), "name": "Legacy clients"},
        )
        conn.execute(
            text("UPDATE projects SET company_id = :cid WHERE company_id IS NULL"),
            {"cid": str(default_id)},
        )


def ensure_website_role_schema(engine: Engine) -> None:
    """Add websites.role for primary vs competitor sites."""
    insp = inspect(engine)
    if "websites" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("websites")}
    if "role" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE websites "
                "ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'primary'"
            )
        )
