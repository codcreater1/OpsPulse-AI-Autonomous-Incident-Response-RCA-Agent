"""Alembic migrations must produce exactly the schema the SQLAlchemy models describe."""

import pathlib

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from src.db.models import Base

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _upgrade(tmp_path, revision="head"):
    engine = create_engine(f"sqlite:///{tmp_path / 'migrations.db'}")
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, revision)
    return engine, cfg


def test_upgrade_head_matches_models(tmp_path):
    engine, _ = _upgrade(tmp_path)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []


def test_0002_adds_category_column_and_approval_table(tmp_path):
    engine, cfg = _upgrade(tmp_path, "0001")
    assert "error_category" not in {c["name"] for c in inspect(engine).get_columns("incidents")}
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
    inspector = inspect(engine)
    assert "error_category" in {c["name"] for c in inspector.get_columns("incidents")}
    assert "remediation_approvals" in inspector.get_table_names()
