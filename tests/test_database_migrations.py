import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

from alembic import command
from alembic.util import CommandError
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from backend.app.database.engine import get_engine
from backend.app.database.migration_runtime import alembic_config, migration_connection
from backend.app.database.models import Base
from backend.app.database.schema import initialize_database


class DatabaseMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.path = self.directory / "tracker.sqlite"
        self.url = f"sqlite:///{self.path}"
        self.engine = get_engine(self.url)
        self.addCleanup(self.engine.dispose)

    def test_fresh_migrated_schema_matches_model_created_schema(self):
        original = get_engine("sqlite://")
        self.addCleanup(original.dispose)
        Base.metadata.create_all(original)
        initialize_database(self.engine)

        self.assertEqual(self._schema_signature(self.engine), self._schema_signature(original))
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text("SELECT version_num FROM alembic_version")), "0001")
            self.assertEqual(connection.scalar(text("SELECT COUNT(*) FROM users")), 0)
            self.assertEqual(connection.scalar(text("PRAGMA foreign_keys")), 1)
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_key_check").all(), [])

    @staticmethod
    def _schema_signature(engine):
        inspector = inspect(engine)
        return {
            table: {
                "columns": [
                    (column["name"], str(column["type"]), column["nullable"], column["default"])
                    for column in inspector.get_columns(table)
                ],
                "primary_key": inspector.get_pk_constraint(table),
                "foreign_keys": sorted(inspector.get_foreign_keys(table), key=lambda fk: fk["constrained_columns"]),
                "unique_constraints": sorted(inspector.get_unique_constraints(table), key=lambda unique: unique["name"]),
                "check_constraints": inspector.get_check_constraints(table),
                "indexes": {
                    index["name"]: (
                        index["column_names"], index["unique"],
                        str(index.get("dialect_options", {}).get("sqlite_where", "")),
                    )
                    for index in inspector.get_indexes(table)
                },
            }
            for table in inspector.get_table_names()
            if table != "alembic_version"
        }

    def test_legacy_schema_requires_explicit_stamp_and_keeps_existing_data(self):
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO users (id, slug, display_name, is_active) "
                "VALUES (5, 'jacob', 'Existing profile', 1), (6, 'other', 'Other', 1)"
            ))
        with self.assertRaisesRegex(CommandError, "unversioned schema"):
            initialize_database(self.engine)
        with closing(sqlite3.connect(self.path)) as connection:
            before = list(connection.iterdump())
            self.assertFalse(any("alembic_version" in row for row in before))

        config = alembic_config()
        with patch.dict(os.environ, {"DATABASE_URL": self.url}):
            # The operator first verifies the legacy schema against the baseline.
            command.stamp(config, "0001")
            command.upgrade(config, "head")
        initialize_database(self.engine)
        initialize_database(self.engine)

        with closing(sqlite3.connect(self.path)) as connection:
            result = [line for line in connection.iterdump() if "alembic_version" not in line]
        self.assertEqual(result, before)

    def test_empty_version_table_does_not_bypass_legacy_guard(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
            connection.exec_driver_sql("CREATE TABLE legacy (data TEXT)")
        with self.assertRaisesRegex(CommandError, "unversioned schema"):
            initialize_database(self.engine)

    def _add_test_revision(self, body: str):
        config = alembic_config()
        revisions = Path(config.get_main_option("script_location")) / "versions"
        config.set_main_option("version_locations", os.pathsep.join([str(revisions), str(self.directory)]))
        (self.directory / "0002_test_revision.py").write_text(dedent(body))
        return patch("backend.app.database.migration_runtime.alembic_config", return_value=config)

    def test_later_batch_revision_preserves_listens_constraints_and_foreign_keys(self):
        initialize_database(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO users (slug, display_name, is_active) VALUES ('jacob', 'Jacob', 1)")
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO albums (id, album_key, artist, name, source, entry_source, metadata_json) "
                "VALUES (10, 'Album key', 'Artist', 'Title', 'manual', 'manual', '{}')"
            )
            connection.exec_driver_sql(
                "INSERT INTO album_listens (id, user_id, album_id, listened_at, source) "
                "SELECT 50, id, 10, '2026-01-01', 'manual' FROM users WHERE slug = 'jacob'"
            )

        with self._add_test_revision("""
            from alembic import op
            import sqlalchemy as sa

            revision = "0002"
            down_revision = "0001"

            def upgrade():
                with op.batch_alter_table("album_listens", recreate="always") as batch:
                    batch.add_column(sa.Column("provenance", sa.String(), nullable=False, server_default="legacy"))
                op.execute("UPDATE album_listens SET provenance = source")
        """):
            initialize_database(self.engine)
            initialize_database(self.engine)

        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text("SELECT version_num FROM alembic_version")), "0002")
            self.assertEqual(
                connection.execute(text("SELECT id, album_id, listened_at, source, provenance FROM album_listens")).all(),
                [(50, 10, "2026-01-01", "manual", "manual")],
            )
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_key_check").all(), [])
            self.assertEqual(connection.scalar(text("PRAGMA foreign_keys")), 1)
            with self.assertRaises(IntegrityError):
                connection.exec_driver_sql("DELETE FROM albums WHERE id = 10")
            with self.assertRaises(IntegrityError):
                connection.exec_driver_sql(
                    "INSERT INTO album_listens (user_id, album_id, listened_at, source) "
                    "SELECT user_id, album_id, listened_at, source FROM album_listens"
                )

    def test_failed_revision_rolls_back_ddl_and_releases_the_lock(self):
        initialize_database(self.engine)
        with self._add_test_revision("""
            from alembic import op
            import sqlalchemy as sa

            revision = "0002"
            down_revision = "0001"

            def upgrade():
                op.create_table("partial_upgrade", sa.Column("id", sa.Integer(), primary_key=True))
                raise RuntimeError("Simulated migration failure")
        """):
            with self.assertRaisesRegex(RuntimeError, "Simulated migration failure"):
                initialize_database(self.engine)

        initialize_database(self.engine)
        self.assertFalse(inspect(self.engine).has_table("partial_upgrade"))
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text("SELECT version_num FROM alembic_version")), "0001")

    def test_processes_wait_for_the_shared_file_lock_then_initialize(self):
        start = (
            "from backend.app.database.engine import get_engine; "
            "from backend.app.database.schema import initialize_database; "
            "print('ready', flush=True); "
            "initialize_database(get_engine())"
        )
        env = {**os.environ, "DATABASE_URL": self.url}
        children = []
        try:
            with migration_connection(self.engine) as connection:
                for _ in range(2):
                    child = subprocess.Popen(
                        [sys.executable, "-c", start], env=env, stdout=subprocess.PIPE, text=True,
                    )
                    children.append(child)
                    self.assertEqual(child.stdout.readline().strip(), "ready")
                    with self.assertRaises(subprocess.TimeoutExpired):
                        child.wait(timeout=0.2)
                self.assertFalse(inspect(connection).has_table("alembic_version"))
            for child in children:
                self.assertEqual(child.wait(timeout=10), 0)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
                child.stdout.close()

        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text("SELECT version_num FROM alembic_version")), "0001")
            self.assertEqual(connection.scalar(text("SELECT COUNT(*) FROM users")), 0)

    def test_file_lock_times_out_before_starting_sqlite_initialization(self):
        second_engine = get_engine(f"sqlite:///{self.path.as_uri()}?uri=1")
        self.addCleanup(second_engine.dispose)
        with migration_connection(self.engine), patch(
            "backend.app.database.migration_runtime.LOCK_TIMEOUT_SECONDS", 0.1
        ):
            with self.assertRaisesRegex(TimeoutError, "SQLite migration lock"):
                initialize_database(second_engine)
        self.assertFalse(inspect(self.engine).has_table("alembic_version"))

    def test_shared_in_memory_engine_initializes_once(self):
        engine = get_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(initialize_database, engine)
            second = executor.submit(initialize_database, engine)
            first.result(timeout=5)
            second.result(timeout=5)
        with engine.connect() as connection:
            self.assertEqual(connection.scalar(text("SELECT version_num FROM alembic_version")), "0001")
            self.assertEqual(connection.scalar(text("SELECT COUNT(*) FROM users")), 0)
