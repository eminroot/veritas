"""The migration builds exactly what the models describe, and undoes itself."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from veritas.db.base import Base

POSTGIS = {"spatial_ref_sys"}


def ours():
    """Every table the models define, read when a test runs."""
    return {table.name for table in Base.metadata.sorted_tables}


def tables(url):
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def scalar(url, sql):
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return connection.execute(text(sql)).scalar()
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade(scratch_database):
    url, config = scratch_database.url, scratch_database.alembic
    command.upgrade(config, "head")
    assert tables(url) == ours() | POSTGIS | {"alembic_version"}
    assert scalar(url, "SELECT version_num FROM alembic_version") == "0004"
    assert scalar(url, "SELECT postgis_version()").startswith("3.")

    command.downgrade(config, "base")
    assert tables(url) == POSTGIS | {"alembic_version"}
    assert scalar(url, "SELECT count(*) FROM alembic_version") == 0
    trigger_function = "SELECT count(*) FROM pg_proc WHERE proname = 'passports_keep_published'"
    assert scalar(url, trigger_function) == 0

    command.upgrade(config, "head")
    assert tables(url) == ours() | POSTGIS | {"alembic_version"}


def test_models_match_the_migration(engine):
    def only_ours(obj, name, type_, reflected, compare_to):
        return type_ != "table" or name in ours()

    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={
                "include_object": only_ours,
                "compare_type": True,
                "compare_server_default": True,
            },
        )
        assert compare_metadata(context, Base.metadata) == []


def test_constraint_and_index_names_follow_the_naming_convention(engine):
    expected = set()
    for table in Base.metadata.sorted_tables:
        expected |= {constraint.name for constraint in table.constraints}
        expected |= {index.name for index in table.indexes}
    with engine.connect() as connection:
        constraints = connection.execute(
            text(
                "SELECT c.conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid"
                " WHERE t.relname = ANY(:tables) AND c.contype IN ('p', 'f', 'u', 'c')"
            ),
            {"tables": sorted(ours())},
        ).scalars()
        indexes = connection.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = ANY(:tables)"),
            {"tables": sorted(ours())},
        ).scalars()
        actual = set(constraints) | set(indexes)
    assert None not in expected
    assert actual == expected
