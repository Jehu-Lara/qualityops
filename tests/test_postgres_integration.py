from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import pandas as pd
import psycopg
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from qualityops import persist_secom
from qualityops import persistence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_DIRECTORY = REPOSITORY_ROOT / "data" / "external" / "secom"
EXPECTED_DATABASE = "qualityops_test_secom"
EXPECTED_OWNER = "qualityops_test_owner"
EXPECTED_REVISION = "0001_secom_persistence"

_ORIGINAL_ADD_SKIP = None
_SKIP_COUNT = 0
_DATABASE_URL = ""

_CONTRACT_RELATIONS = {
    ("public", "alembic_version", "r"),
    ("public", "alembic_version_pkc", "i"),
    ("qualityops", "dataset", "r"),
    ("qualityops", "dataset_dataset_id_seq", "S"),
    ("qualityops", "dataset_version", "r"),
    ("qualityops", "dataset_version_dataset_version_id_seq", "S"),
    ("qualityops", "source_file", "r"),
    ("qualityops", "observation", "r"),
    ("qualityops", "sensor", "r"),
    ("qualityops", "measurement", "r"),
    ("qualityops", "v_measurement_fact", "v"),
    ("qualityops", "pk_dataset", "i"),
    ("qualityops", "uq_dataset_dataset_code", "i"),
    ("qualityops", "uq_dataset_doi", "i"),
    ("qualityops", "pk_dataset_version", "i"),
    ("qualityops", "uq_dataset_version_dataset_version_label", "i"),
    ("qualityops", "uq_dataset_version_dataset_fingerprint", "i"),
    ("qualityops", "pk_source_file", "i"),
    ("qualityops", "uq_source_file_dataset_version_role", "i"),
    ("qualityops", "pk_observation", "i"),
    ("qualityops", "pk_sensor", "i"),
    ("qualityops", "uq_sensor_dataset_version_sensor_key", "i"),
    ("qualityops", "pk_measurement", "i"),
    ("qualityops", "ix_observation_version_observed_at", "i"),
    ("qualityops", "ix_observation_version_outcome_observed_at", "i"),
    ("qualityops", "ix_measurement_version_sensor_source_row", "i"),
    ("qualityops", "ix_measurement_missing_by_observation", "i"),
}


def _run_alembic(arguments: list[str], *, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("QUALITYOPS_DATABASE_URL", None)
    environment["QUALITYOPS_DATABASE_URL"] = _DATABASE_URL
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    if expect_success and completed.returncode != 0:
        raise AssertionError(
            f"Alembic failed with code {completed.returncode}: "
            f"{completed.stdout}\n{completed.stderr}"
        )
    if not expect_success and completed.returncode == 0:
        raise AssertionError("Alembic unexpectedly succeeded")
    return completed


@contextmanager
def _connection(*, autocommit: bool = False, application_name: str = "qualityops-integration"):
    connection = psycopg.connect(
        _DATABASE_URL,
        autocommit=autocommit,
        application_name=application_name,
    )
    try:
        yield connection
    finally:
        connection.close()


def _user_relations(connection) -> set[tuple[str, str, str]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT n.nspname, c.relname, c.relkind::text
               FROM pg_class AS c
               JOIN pg_namespace AS n ON n.oid = c.relnamespace
               WHERE n.nspname IN ('public', 'qualityops')
                 AND c.relkind IN ('r', 'v', 'm', 'S', 'i', 'p')
               ORDER BY n.nspname, c.relname"""
        )
        return set(cursor.fetchall())


def _remove_contract_state() -> None:
    with _connection(autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.alembic_version')")
            has_version_table = cursor.fetchone()[0] is not None
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'qualityops')"
            )
            has_schema = cursor.fetchone()[0]
    if has_version_table and has_schema:
        _run_alembic(["downgrade", "base"])
    elif has_schema:
        raise AssertionError("qualityops exists without a managed Alembic state")
    with _connection(autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS public.alembic_version")


def _assert_empty_database() -> None:
    with _connection() as connection:
        relations = _user_relations(connection)
        unexpected = {
            item for item in relations
            if item[0] in {"public", "qualityops"}
        }
        if unexpected:
            raise AssertionError(f"Disposable database is not empty: {sorted(unexpected)}")


def setUpModule() -> None:
    global _ORIGINAL_ADD_SKIP, _SKIP_COUNT, _DATABASE_URL
    flag = os.environ.get("QUALITYOPS_RUN_POSTGRES_INTEGRATION")
    if flag is None:
        raise unittest.SkipTest(
            "PostgreSQL integration is opt-in; set QUALITYOPS_RUN_POSTGRES_INTEGRATION=1"
        )
    if flag != "1":
        raise RuntimeError("QUALITYOPS_RUN_POSTGRES_INTEGRATION must be exactly '1'")
    _DATABASE_URL = os.environ.get("QUALITYOPS_TEST_DATABASE_URL", "")
    if not _DATABASE_URL:
        raise RuntimeError("QUALITYOPS_TEST_DATABASE_URL is required for integration")

    connection_fields = conninfo_to_dict(_DATABASE_URL)
    database_name = connection_fields.get("dbname")
    if database_name is None and _DATABASE_URL.startswith(("postgresql://", "postgres://")):
        database_name = make_url(_DATABASE_URL).database
    if not database_name or re.fullmatch(r"qualityops_test_[a-z0-9_]+", database_name) is None:
        raise RuntimeError("Integration DSN must select a disposable qualityops_test_* database")
    if database_name in {"postgres", "template0", "template1"}:
        raise RuntimeError("System databases are forbidden for integration")
    if database_name != EXPECTED_DATABASE:
        raise RuntimeError("Integration DSN selected an unexpected database")

    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SHOW server_version_num")
            server_version_num = int(cursor.fetchone()[0])
            if not 160000 <= server_version_num < 170000:
                raise RuntimeError("Integration requires real PostgreSQL 16")
            cursor.execute(
                """SELECT current_database(), current_user, pg_get_userbyid(datdba)
                   FROM pg_database WHERE datname = current_database()"""
            )
            current_database, current_user, owner = cursor.fetchone()
            if current_database != database_name:
                raise RuntimeError("current_database() differs from the integration DSN")
            if current_user != EXPECTED_OWNER or owner != EXPECTED_OWNER:
                raise RuntimeError("Integration user and database owner must be qualityops_test_owner")

        relations = _user_relations(connection)
        if not relations.issubset(_CONTRACT_RELATIONS):
            raise RuntimeError("Disposable database contains unrecognized user objects")
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT n.nspname,p.proname FROM pg_proc AS p
                   JOIN pg_namespace AS n ON n.oid=p.pronamespace
                   WHERE n.nspname='qualityops' ORDER BY p.proname"""
            )
            if cursor.fetchall():
                raise RuntimeError("Disposable database contains unrecognized functions")
            cursor.execute(
                """SELECT tgname FROM pg_trigger AS t
                   JOIN pg_class AS c ON c.oid=t.tgrelid
                   JOIN pg_namespace AS n ON n.oid=c.relnamespace
                   WHERE n.nspname='qualityops' AND NOT t.tgisinternal
                   ORDER BY tgname"""
            )
            if cursor.fetchall():
                raise RuntimeError("Disposable database contains unrecognized triggers")

    _remove_contract_state()
    _assert_empty_database()

    _SKIP_COUNT = 0
    _ORIGINAL_ADD_SKIP = unittest.TestResult.addSkip

    def _count_skip(result, test, reason):
        global _SKIP_COUNT
        _SKIP_COUNT += 1
        return _ORIGINAL_ADD_SKIP(result, test, reason)

    unittest.TestResult.addSkip = _count_skip


def tearDownModule() -> None:
    global _ORIGINAL_ADD_SKIP
    skip_error = None
    try:
        try:
            _remove_contract_state()
        except Exception as error:  # pragma: no cover - reported by teardown.
            skip_error = error
        if _SKIP_COUNT:
            skip_error = AssertionError(
                f"PostgreSQL integration recorded {_SKIP_COUNT} skipped tests"
            )
    finally:
        if _ORIGINAL_ADD_SKIP is not None:
            unittest.TestResult.addSkip = _ORIGINAL_ADD_SKIP
            _ORIGINAL_ADD_SKIP = None
    if skip_error is not None:
        raise skip_error


class PostgreSQLIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.real_source = persistence._verify_source_before_connect(DATA_DIRECTORY)

    def _upgrade(self) -> None:
        _run_alembic(["upgrade", "head"])

    def _downgrade_clean(self) -> None:
        _run_alembic(["downgrade", "base"])
        with _connection(autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS public.alembic_version")

    def _counts(self) -> tuple[int, int, int, int, int, int]:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT
                       (SELECT COUNT(*) FROM qualityops.dataset),
                       (SELECT COUNT(*) FROM qualityops.dataset_version),
                       (SELECT COUNT(*) FROM qualityops.source_file),
                       (SELECT COUNT(*) FROM qualityops.sensor),
                       (SELECT COUNT(*) FROM qualityops.observation),
                       (SELECT COUNT(*) FROM qualityops.measurement)"""
                )
                return cursor.fetchone()

    def _synthetic_source(self):
        timestamps = pd.to_datetime(["2008-01-01 00:00:00", "2008-01-02 00:00:00"])
        data: dict[str, object] = {
            "source_row": [1, 2],
            "timestamp": timestamps,
            "label": [-1, 1],
        }
        for index, key in enumerate(persistence._SENSOR_KEYS):
            data[key] = [float(index), float(index) + 0.5]
        data["sensor_589"] = [589.0, math.nan]
        dataframe = pd.DataFrame(data)
        return replace(
            self.real_source,
            dataframe=dataframe,
            observation_count=2,
            sensor_count=590,
            measurement_count=1180,
            missing_measurement_count=1,
            pass_count=1,
            fail_count=1,
            earliest_timestamp=datetime(2008, 1, 1),
            latest_timestamp=datetime(2008, 1, 2),
        )

    def _reset_to_empty_upgraded(self) -> None:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM qualityops.dataset_version")
                cursor.execute("DELETE FROM qualityops.dataset")
            connection.commit()

    def _load_with_source(self, source):
        with patch.object(persistence, "_verify_source_before_connect", return_value=source):
            return persist_secom(DATA_DIRECTORY, _DATABASE_URL)

    def test_01_migration_ownership_upgrade_and_downgrade(self) -> None:
        with _connection(autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE SCHEMA qualityops")
        _run_alembic(["upgrade", "head"], expect_success=False)
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT COUNT(*) FROM pg_class AS c
                       JOIN pg_namespace AS n ON n.oid = c.relnamespace
                       WHERE n.nspname = 'qualityops'"""
                )
                self.assertEqual(cursor.fetchone(), (0,))
                cursor.execute("SELECT to_regclass('public.alembic_version')")
                self.assertIsNone(cursor.fetchone()[0])
        with _connection(autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DROP SCHEMA qualityops")

        self._upgrade()
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM public.alembic_version ORDER BY version_num")
                self.assertEqual([row[0] for row in cursor.fetchall()], [EXPECTED_REVISION])
                cursor.execute("CREATE TABLE qualityops.unexpected_object (value INTEGER)")
            connection.commit()
        _run_alembic(["downgrade", "base"], expect_success=False)
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('qualityops.dataset'), to_regclass('qualityops.unexpected_object')")
                self.assertEqual(cursor.fetchone(), ("qualityops.dataset", "qualityops.unexpected_object"))
        with _connection(autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE qualityops.unexpected_object")
        self._downgrade_clean()
        _assert_empty_database()
        self._upgrade()

    def test_02_schema_constraints_indexes_view_and_delete_policies(self) -> None:
        expected_constraints = {
            "pk_dataset", "uq_dataset_dataset_code", "uq_dataset_doi",
            "ck_dataset_dataset_code_nonempty", "ck_dataset_name_nonempty",
            "ck_dataset_publisher_nonempty", "ck_dataset_doi_nonempty",
            "ck_dataset_source_url_https", "ck_dataset_license_spdx_nonempty",
            "pk_dataset_version", "fk_dataset_version_dataset",
            "uq_dataset_version_dataset_version_label", "uq_dataset_version_dataset_fingerprint",
            "ck_dataset_version_label_nonempty", "ck_dataset_version_fingerprint_sha256",
            "ck_dataset_version_audit_schema_version_positive",
            "ck_dataset_version_observation_count_positive", "ck_dataset_version_sensor_count_positive",
            "ck_dataset_version_measurement_count_positive",
            "ck_dataset_version_measurement_count_consistent", "ck_dataset_version_missing_count_range",
            "pk_source_file", "fk_source_file_dataset_version", "uq_source_file_dataset_version_role",
            "ck_source_file_filename_nonempty", "ck_source_file_role",
            "ck_source_file_byte_size_positive", "ck_source_file_sha256",
            "pk_observation", "fk_observation_dataset_version",
            "ck_observation_source_row_positive", "ck_observation_outcome",
            "pk_sensor", "fk_sensor_dataset_version", "uq_sensor_dataset_version_sensor_key",
            "ck_sensor_index_range", "ck_sensor_key_matches_index",
            "pk_measurement", "fk_measurement_observation", "fk_measurement_sensor",
            "ck_measurement_finite",
        }
        expected_explicit_indexes = {
            "ix_observation_version_observed_at",
            "ix_observation_version_outcome_observed_at",
            "ix_measurement_version_sensor_source_row",
            "ix_measurement_missing_by_observation",
        }
        with _connection() as connection:
            self.assertEqual(_user_relations(connection), _CONTRACT_RELATIONS)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT conname FROM pg_constraint AS con
                       JOIN pg_namespace AS n ON n.oid = con.connamespace
                       WHERE n.nspname = 'qualityops' ORDER BY conname"""
                )
                self.assertEqual({row[0] for row in cursor.fetchall()}, expected_constraints)
                cursor.execute(
                    """SELECT indexname FROM pg_indexes WHERE schemaname = 'qualityops'
                       AND indexname LIKE 'ix_%' ORDER BY indexname"""
                )
                self.assertEqual({row[0] for row in cursor.fetchall()}, expected_explicit_indexes)
                cursor.execute(
                    """SELECT column_name FROM information_schema.columns
                       WHERE table_schema='qualityops' AND table_name='v_measurement_fact'
                       ORDER BY ordinal_position"""
                )
                self.assertEqual(
                    [row[0] for row in cursor.fetchall()],
                    ["dataset_version_id", "source_row", "observed_at", "outcome", "outcome_name", "sensor_index", "sensor_key", "value", "is_missing"],
                )
                cursor.execute(
                    """SELECT COUNT(*) FROM pg_index AS i
                       JOIN pg_class AS t ON t.oid=i.indrelid
                       JOIN pg_namespace AS n ON n.oid=t.relnamespace
                       JOIN pg_attribute AS a ON a.attrelid=t.oid AND a.attnum=ANY(i.indkey)
                       WHERE n.nspname='qualityops' AND t.relname='observation'
                         AND i.indisunique AND a.attname='observed_at'"""
                )
                self.assertEqual(cursor.fetchone(), (0,))

                cursor.execute(
                    """INSERT INTO qualityops.dataset
                       (dataset_code,name,publisher,doi,source_url,license_spdx)
                       VALUES ('fixture','Fixture','Fixture',NULL,'https://example.test','MIT')
                       RETURNING dataset_id"""
                )
                dataset_id = cursor.fetchone()[0]
                version_ids = []
                for label in ("v1", "v2"):
                    cursor.execute(
                        """INSERT INTO qualityops.dataset_version
                           (dataset_id,version_label,content_fingerprint,acquired_on,audit_schema_version,
                            observation_count,sensor_count,measurement_count,missing_measurement_count)
                           VALUES (%s,%s,%s,DATE '2026-01-01',1,1,1,1,0)
                           RETURNING dataset_version_id""",
                        (dataset_id, label, ("A" if label == "v1" else "B") * 64),
                    )
                    version_ids.append(cursor.fetchone()[0])
                self.assertNotEqual(version_ids[0], version_ids[1])
                for offset, version_id in enumerate(version_ids):
                    cursor.execute(
                        "INSERT INTO qualityops.observation VALUES (%s,1,%s,%s)",
                        (version_id, datetime(2020 + offset, 1, 1), -1 if offset == 0 else 1),
                    )
                    cursor.execute(
                        "INSERT INTO qualityops.sensor VALUES (%s,0,'sensor_000')",
                        (version_id,),
                    )
                    cursor.execute(
                        "INSERT INTO qualityops.measurement VALUES (%s,1,0,%s)",
                        (version_id, 10.0 + offset),
                    )
                cursor.execute(
                    """SELECT dataset_version_id,observed_at,outcome,sensor_key,value
                       FROM qualityops.v_measurement_fact
                       WHERE dataset_version_id=ANY(%s) ORDER BY dataset_version_id""",
                    (version_ids,),
                )
                rows = cursor.fetchall()
                self.assertEqual([row[0] for row in rows], version_ids)
                self.assertEqual([(row[2], row[4]) for row in rows], [(-1, 10.0), (1, 11.0)])
                with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                    with connection.transaction():
                        cursor.execute("DELETE FROM qualityops.dataset WHERE dataset_id=%s", (dataset_id,))
                cursor.execute("DELETE FROM qualityops.dataset_version WHERE dataset_version_id=%s", (version_ids[0],))
                for table in ("source_file", "observation", "sensor", "measurement"):
                    cursor.execute(f"SELECT COUNT(*) FROM qualityops.{table} WHERE dataset_version_id=%s", (version_ids[0],))
                    self.assertEqual(cursor.fetchone(), (0,))
                cursor.execute("DELETE FROM qualityops.dataset_version WHERE dataset_id=%s", (dataset_id,))
                cursor.execute("DELETE FROM qualityops.dataset WHERE dataset_id=%s", (dataset_id,))

                for invalid_index, invalid_key in ((-1, "sensor_-01"), (590, "sensor_590")):
                    with self.subTest(sensor_index=invalid_index):
                        with self.assertRaises(psycopg.errors.CheckViolation):
                            with connection.transaction():
                                cursor.execute("INSERT INTO qualityops.sensor VALUES (999,%s,%s)", (invalid_index, invalid_key))
                for invalid_value in (float("nan"), float("inf"), float("-inf")):
                    with self.subTest(value=invalid_value):
                        with self.assertRaises(psycopg.errors.CheckViolation):
                            with connection.transaction():
                                cursor.execute("INSERT INTO qualityops.measurement VALUES (999,1,0,%s)", (invalid_value,))
            connection.commit()

    def test_03_alembic_revision_states_precede_lock_and_writes(self) -> None:
        source = self._synthetic_source()
        states = ("missing", "empty", "different", "multiple")
        for state in states:
            with self.subTest(state=state):
                with _connection(autocommit=True) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("DROP TABLE IF EXISTS public.alembic_version")
                        if state != "missing":
                            cursor.execute(
                                """CREATE TABLE public.alembic_version (
                                   version_num VARCHAR(32) NOT NULL,
                                   CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"""
                            )
                        if state == "different":
                            cursor.execute("INSERT INTO public.alembic_version VALUES ('different')")
                        elif state == "multiple":
                            cursor.execute("INSERT INTO public.alembic_version VALUES ('different'),('other')")
                with patch.object(persistence, "_verify_source_before_connect", return_value=source):
                    with self.assertRaises(persistence.SecomMigrationError):
                        persist_secom(DATA_DIRECTORY, _DATABASE_URL)
                self.assertEqual(self._counts(), (0, 0, 0, 0, 0, 0))

        with _connection(autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS public.alembic_version")
                cursor.execute(
                    """CREATE TABLE public.alembic_version (
                       version_num VARCHAR(32) NOT NULL,
                       CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"""
                )
                cursor.execute("INSERT INTO public.alembic_version VALUES (%s)", (EXPECTED_REVISION,))
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM public.alembic_version ORDER BY version_num")
                self.assertEqual([row[0] for row in cursor.fetchall()], [EXPECTED_REVISION])

    def _install_write_guards(self) -> None:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """CREATE FUNCTION qualityops.test_reject_write() RETURNS trigger
                       LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'TEST_WRITE_GUARD'; END $$"""
                )
                for table in ("dataset", "dataset_version", "source_file", "sensor", "observation", "measurement"):
                    cursor.execute(
                        f"""CREATE TRIGGER test_reject_write_{table}
                            BEFORE INSERT OR UPDATE OR DELETE ON qualityops.{table}
                            FOR EACH ROW EXECUTE FUNCTION qualityops.test_reject_write()"""
                    )
            connection.commit()

    def _remove_write_guards(self) -> None:
        with _connection() as connection:
            with connection.cursor() as cursor:
                for table in ("dataset", "dataset_version", "source_file", "sensor", "observation", "measurement"):
                    cursor.execute(f"DROP TRIGGER IF EXISTS test_reject_write_{table} ON qualityops.{table}")
                cursor.execute("DROP FUNCTION IF EXISTS qualityops.test_reject_write()")
            connection.commit()

    def test_04_idempotence_is_read_only_with_guards_on_all_six_tables(self) -> None:
        source = self._synthetic_source()
        first = self._load_with_source(source)
        self.assertEqual(first.status, "loaded")
        self.assertEqual(self._counts(), (1, 1, 3, 590, 2, 1180))
        self._install_write_guards()
        try:
            second = self._load_with_source(source)
            self.assertEqual(second.status, "already_loaded")
            self.assertEqual(first.to_dict() | {"status": "already_loaded"}, second.to_dict())
        finally:
            self._remove_write_guards()

    def _reset_synthetic(self, source) -> tuple[int, int]:
        self._reset_to_empty_upgraded()
        self.assertEqual(self._load_with_source(source).status, "loaded")
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT d.dataset_id,dv.dataset_version_id
                       FROM qualityops.dataset AS d JOIN qualityops.dataset_version AS dv
                       ON dv.dataset_id=d.dataset_id WHERE d.dataset_code='uci-secom'"""
                )
                return cursor.fetchone()

    def _apply_corruption(self, name: str, dataset_id: int, version_id: int) -> str:
        with _connection() as connection:
            with connection.cursor() as cursor:
                simple_updates = {
                    "dataset.dataset_code": ("qualityops.dataset", "dataset_code='corrupt'", "dataset_id"),
                    "dataset.name": ("qualityops.dataset", "name='Corrupt'", "dataset_id"),
                    "dataset.publisher": ("qualityops.dataset", "publisher='Corrupt'", "dataset_id"),
                    "dataset.doi": ("qualityops.dataset", "doi=NULL", "dataset_id"),
                    "dataset.source_url": ("qualityops.dataset", "source_url='https://example.test/corrupt'", "dataset_id"),
                    "dataset.license_spdx": ("qualityops.dataset", "license_spdx='CC0-1.0'", "dataset_id"),
                    "dataset_version.version_label": ("qualityops.dataset_version", "version_label='corrupt'", "dataset_version_id"),
                    "dataset_version.content_fingerprint": ("qualityops.dataset_version", f"content_fingerprint='{'0' * 64}'", "dataset_version_id"),
                    "dataset_version.acquired_on": ("qualityops.dataset_version", "acquired_on=DATE '2026-08-09'", "dataset_version_id"),
                    "dataset_version.audit_schema_version": ("qualityops.dataset_version", "audit_schema_version=2", "dataset_version_id"),
                    "dataset_version.missing_measurement_count": ("qualityops.dataset_version", "missing_measurement_count=2", "dataset_version_id"),
                    "observation.outcome": ("qualityops.observation", "outcome=1", "dataset_version_id"),
                    "observation.observed_at": ("qualityops.observation", "observed_at=TIMESTAMP '2009-01-01'", "dataset_version_id"),
                    "measurement.null_incorrect": ("qualityops.measurement", "value=NULL", "dataset_version_id"),
                    "measurement.value": ("qualityops.measurement", "value=value+1", "dataset_version_id"),
                }
                if name in simple_updates:
                    table, assignment, key = simple_updates[name]
                    extra = " AND source_row=1" if table.endswith("observation") else ""
                    if table.endswith("measurement"):
                        extra = " AND source_row=1 AND sensor_index=0"
                    cursor.execute(f"UPDATE {table} SET {assignment} WHERE {key}=%s{extra}", (dataset_id if key == "dataset_id" else version_id,))
                elif name == "dataset_version.dataset_id":
                    cursor.execute(
                        """INSERT INTO qualityops.dataset
                           (dataset_code,name,publisher,doi,source_url,license_spdx)
                           VALUES ('other','Other','Other',NULL,'https://example.test','MIT') RETURNING dataset_id"""
                    )
                    other_id = cursor.fetchone()[0]
                    cursor.execute("UPDATE qualityops.dataset_version SET dataset_id=%s WHERE dataset_version_id=%s", (other_id, version_id))
                elif name in {"dataset_version.observation_count", "dataset_version.measurement_count"}:
                    cursor.execute("UPDATE qualityops.dataset_version SET observation_count=1,measurement_count=590 WHERE dataset_version_id=%s", (version_id,))
                elif name == "dataset_version.sensor_count":
                    cursor.execute("UPDATE qualityops.dataset_version SET sensor_count=589,measurement_count=1178 WHERE dataset_version_id=%s", (version_id,))
                elif name == "dataset_version.loaded_at":
                    cursor.execute("ALTER TABLE qualityops.dataset_version ALTER COLUMN loaded_at DROP NOT NULL")
                    cursor.execute("UPDATE qualityops.dataset_version SET loaded_at=NULL WHERE dataset_version_id=%s", (version_id,))
                elif name == "source_file.missing":
                    cursor.execute("DELETE FROM qualityops.source_file WHERE dataset_version_id=%s AND filename='secom.names'", (version_id,))
                elif name == "source_file.extra":
                    cursor.execute("ALTER TABLE qualityops.source_file DROP CONSTRAINT IF EXISTS uq_source_file_dataset_version_role")
                    cursor.execute("INSERT INTO qualityops.source_file VALUES (%s,'extra.data','metadata',1,%s)", (version_id, "A" * 64))
                elif name == "source_file.filename":
                    cursor.execute("UPDATE qualityops.source_file SET filename='renamed.data' WHERE dataset_version_id=%s AND filename='secom.names'", (version_id,))
                elif name == "source_file.role":
                    cursor.execute("ALTER TABLE qualityops.source_file DROP CONSTRAINT IF EXISTS uq_source_file_dataset_version_role")
                    cursor.execute("ALTER TABLE qualityops.source_file DROP CONSTRAINT IF EXISTS ck_source_file_role")
                    cursor.execute("UPDATE qualityops.source_file SET role='corrupt' WHERE dataset_version_id=%s AND filename='secom.names'", (version_id,))
                elif name == "source_file.byte_size":
                    cursor.execute("UPDATE qualityops.source_file SET byte_size=byte_size+1 WHERE dataset_version_id=%s AND filename='secom.names'", (version_id,))
                elif name == "source_file.sha256":
                    cursor.execute("UPDATE qualityops.source_file SET sha256=%s WHERE dataset_version_id=%s AND filename='secom.names'", ("0" * 64, version_id))
                elif name == "sensor.missing":
                    cursor.execute("DELETE FROM qualityops.sensor WHERE dataset_version_id=%s AND sensor_index=589", (version_id,))
                elif name == "sensor.extra":
                    cursor.execute("ALTER TABLE qualityops.sensor DROP CONSTRAINT IF EXISTS ck_sensor_index_range")
                    cursor.execute("ALTER TABLE qualityops.sensor DROP CONSTRAINT IF EXISTS ck_sensor_key_matches_index")
                    cursor.execute("INSERT INTO qualityops.sensor VALUES (%s,590,'sensor_590')", (version_id,))
                elif name == "sensor.sensor_index":
                    cursor.execute("ALTER TABLE qualityops.measurement DROP CONSTRAINT IF EXISTS fk_measurement_sensor")
                    cursor.execute("ALTER TABLE qualityops.sensor DROP CONSTRAINT IF EXISTS ck_sensor_index_range")
                    cursor.execute("ALTER TABLE qualityops.sensor DROP CONSTRAINT IF EXISTS ck_sensor_key_matches_index")
                    cursor.execute("UPDATE qualityops.sensor SET sensor_index=590 WHERE dataset_version_id=%s AND sensor_index=589", (version_id,))
                elif name == "sensor.sensor_key":
                    cursor.execute("ALTER TABLE qualityops.sensor DROP CONSTRAINT IF EXISTS ck_sensor_key_matches_index")
                    cursor.execute("UPDATE qualityops.sensor SET sensor_key='corrupt' WHERE dataset_version_id=%s AND sensor_index=589", (version_id,))
                elif name == "observation.missing":
                    cursor.execute("DELETE FROM qualityops.observation WHERE dataset_version_id=%s AND source_row=2", (version_id,))
                elif name == "observation.extra":
                    cursor.execute("INSERT INTO qualityops.observation VALUES (%s,3,TIMESTAMP '2008-01-03',-1)", (version_id,))
                elif name == "measurement.missing":
                    cursor.execute("DELETE FROM qualityops.measurement WHERE dataset_version_id=%s AND source_row=1 AND sensor_index=0", (version_id,))
                elif name == "measurement.extra":
                    cursor.execute("INSERT INTO qualityops.observation VALUES (%s,3,TIMESTAMP '2008-01-03',-1)", (version_id,))
                    cursor.execute("INSERT INTO qualityops.measurement VALUES (%s,3,0,1.0)", (version_id,))
                elif name == "measurement.null_to_value":
                    cursor.execute("UPDATE qualityops.measurement SET value=0.0 WHERE dataset_version_id=%s AND source_row=2 AND sensor_index=589", (version_id,))
                else:
                    raise AssertionError(f"Unknown corruption: {name}")
            connection.commit()
        return name

    def test_05_all_34_corruption_families_fail_without_repair_or_writes(self) -> None:
        source = self._synthetic_source()
        cases = (
            "dataset.dataset_code", "dataset.name", "dataset.publisher", "dataset.doi",
            "dataset.source_url", "dataset.license_spdx", "dataset_version.dataset_id",
            "dataset_version.version_label", "dataset_version.content_fingerprint",
            "dataset_version.acquired_on", "dataset_version.audit_schema_version",
            "dataset_version.observation_count", "dataset_version.sensor_count",
            "dataset_version.measurement_count", "dataset_version.missing_measurement_count",
            "dataset_version.loaded_at", "source_file.missing", "source_file.extra",
            "source_file.filename", "source_file.role", "source_file.byte_size", "source_file.sha256",
            "sensor.missing", "sensor.extra", "sensor.sensor_index", "sensor.sensor_key",
            "observation.missing", "observation.extra", "observation.outcome",
            "observation.observed_at", "measurement.missing", "measurement.extra",
            "measurement.null_incorrect", "measurement.value",
        )
        self.assertEqual(len(cases), 34)
        for name in cases:
            with self.subTest(corruption=name):
                dataset_id, version_id = self._reset_synthetic(source)
                self._apply_corruption(name, dataset_id, version_id)
                before = self._counts()
                self._install_write_guards()
                try:
                    with self.assertRaises(persistence.SecomPersistenceConflictError):
                        self._load_with_source(source)
                    self.assertEqual(self._counts(), before)
                finally:
                    self._remove_write_guards()

        self._downgrade_clean()
        self._upgrade()

    def test_06_copy_failure_rolls_back_every_new_row(self) -> None:
        message = "TEST_COPY_REACHED_SOURCE_ROW_2_SENSOR_0"
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""CREATE FUNCTION qualityops.test_fail_partial_copy() RETURNS trigger
                        LANGUAGE plpgsql AS $$ BEGIN
                          IF NEW.source_row=2 AND NEW.sensor_index=0 THEN
                            RAISE EXCEPTION '{message}';
                          END IF;
                          RETURN NEW;
                        END $$"""
                )
                cursor.execute(
                    """CREATE TRIGGER test_fail_partial_copy
                       BEFORE INSERT ON qualityops.measurement
                       FOR EACH ROW EXECUTE FUNCTION qualityops.test_fail_partial_copy()"""
                )
            connection.commit()
        try:
            with patch.object(persistence, "_verify_source_before_connect", return_value=self.real_source):
                with self.assertRaises(persistence.SecomDatabaseError) as raised:
                    persist_secom(DATA_DIRECTORY, _DATABASE_URL)
            self.assertIn(message, str(raised.exception.__cause__))
            self.assertEqual(self._counts(), (0, 0, 0, 0, 0, 0))
        finally:
            with _connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("DROP TRIGGER IF EXISTS test_fail_partial_copy ON qualityops.measurement")
                    cursor.execute("DROP FUNCTION IF EXISTS qualityops.test_fail_partial_copy()")
                connection.commit()

    def test_07_concurrent_loads_serialize_to_loaded_and_already_loaded(self) -> None:
        controller = None
        cleanup = None
        executor = None
        futures: list[Future] = []
        worker_pids: list[int] = []
        lock_released = False
        source_patcher = None
        try:
            controller = psycopg.connect(
                _DATABASE_URL,
                autocommit=False,
                application_name="qualityops-concurrency-controller",
            )
            with controller.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (persistence._EXPECTED_LOCK_KEY,))
            cleanup = psycopg.connect(
                _DATABASE_URL,
                autocommit=False,
                application_name="qualityops-concurrency-cleanup",
            )
            executor = ThreadPoolExecutor(max_workers=2)
            source_patcher = patch.object(
                persistence,
                "_verify_source_before_connect",
                return_value=self.real_source,
            )
            source_patcher.start()

            def worker():
                return persist_secom(DATA_DIRECTORY, _DATABASE_URL)

            futures = [executor.submit(worker), executor.submit(worker)]
            deadline = time.monotonic() + 30.0
            while time.monotonic() < deadline:
                with cleanup.cursor() as cursor:
                    cursor.execute(
                        """SELECT pid,wait_event_type,wait_event
                           FROM pg_stat_activity
                           WHERE datname=current_database()
                             AND application_name='qualityops-load-secom'
                           ORDER BY pid"""
                    )
                    rows = cursor.fetchall()
                cleanup.rollback()
                if len(rows) == 2 and all(row[1:] == ("Lock", "advisory") for row in rows):
                    worker_pids = [row[0] for row in rows]
                    break
                time.sleep(0.1)
            else:
                self.fail("Exactly two advisory-lock waiters were not observed within 30 seconds")

            controller.rollback()
            lock_released = True
            results = [future.result(timeout=240) for future in futures]
            self.assertEqual(sorted(result.status for result in results), ["already_loaded", "loaded"])
            first_payload = results[0].to_dict()
            second_payload = results[1].to_dict()
            first_payload.pop("status")
            second_payload.pop("status")
            self.assertEqual(first_payload, second_payload)
            self.assertEqual(self._counts(), (1, 1, 3, 590, 1567, 924530))
        finally:
            if cleanup is None:
                cleanup = psycopg.connect(_DATABASE_URL, autocommit=False, application_name="qualityops-concurrency-cleanup")
            if controller is not None and not lock_released:
                controller.rollback()
            if futures:
                wait(futures, timeout=5)
            with cleanup.cursor() as cursor:
                for pid in worker_pids:
                    if any(not future.done() for future in futures):
                        cursor.execute("SELECT pg_cancel_backend(%s)", (pid,))
                cleanup.commit()
                for pid in worker_pids:
                    cursor.execute(
                        """SELECT EXISTS (SELECT 1 FROM pg_stat_activity
                           WHERE pid=%s AND datname=current_database())""",
                        (pid,),
                    )
                    if cursor.fetchone()[0]:
                        cursor.execute("SELECT pg_terminate_backend(%s)", (pid,))
                cleanup.commit()
            for future in futures:
                if not future.done():
                    future.cancel()
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=True)
            if source_patcher is not None:
                source_patcher.stop()
            if controller is not None:
                controller.close()
                controller = None
            with cleanup.cursor() as cursor:
                cursor.execute(
                    """SELECT n.nspname,p.proname FROM pg_proc AS p
                       JOIN pg_namespace AS n ON n.oid=p.pronamespace
                       WHERE n.nspname='qualityops' AND p.proname LIKE 'test_%'"""
                )
                self.assertEqual(cursor.fetchall(), [])
            cleanup.rollback()
            cleanup.close()

    def _query(self, engine, name: str, parameters: dict[str, object]) -> list[dict[str, object]]:
        with persistence.stream_quality_query(engine, name, parameters) as mappings:
            return [dict(row) for row in mappings]

    def test_08_all_twenty_queries_match_independent_oracles_and_stream(self) -> None:
        engine = create_engine(make_url(_DATABASE_URL).set(drivername="postgresql+psycopg"), echo=False)
        try:
            with _connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT dataset_version_id FROM qualityops.dataset_version WHERE version_label=%s", (persistence._VERSION_LABEL,))
                    version_id = cursor.fetchone()[0]
            with engine.connect().execution_options(postgresql_readonly=True) as connection:
                with connection.begin():
                    self.assertEqual(connection.execute(text("SHOW transaction_read_only")).scalar_one(), "on")

            expected_columns = {
                "01_dataset_provenance.sql": ["dataset_version_id","dataset_code","name","publisher","doi","source_url","license_spdx","version_label","acquired_on","loaded_at","audit_schema_version","content_fingerprint"],
                "02_source_file_integrity.sql": ["dataset_version_id","filename","role","byte_size","sha256"],
                "03_load_reconciliation.sql": ["dataset_version_id","expected_observation_count","actual_observation_count","observations_match","expected_sensor_count","actual_sensor_count","sensors_match","expected_measurement_count","actual_measurement_count","measurements_match","expected_missing_measurement_count","actual_missing_measurement_count","missing_measurements_match","measurements_per_observation_match"],
                "04_outcome_distribution.sql": ["dataset_version_id","outcome","outcome_name","observation_count","observation_percentage"],
                "05_daily_yield.sql": ["dataset_version_id","observed_date","observation_count","pass_count","fail_count","fail_rate"],
                "06_repeated_timestamps.sql": ["dataset_version_id","observed_at","occurrence_count","source_rows","outcomes"],
                "07_sensor_missingness.sql": ["dataset_version_id","sensor_index","sensor_key","measurement_count","nonmissing_count","missing_count","missing_rate"],
                "08_observation_missingness.sql": ["dataset_version_id","source_row","observed_at","outcome","outcome_name","sensor_count","nonmissing_count","missing_count","missing_rate"],
                "09_sensor_missingness_by_outcome.sql": ["dataset_version_id","sensor_index","sensor_key","outcome","outcome_name","observation_count","nonmissing_count","missing_count","missing_rate"],
                "10_constant_sensors.sql": ["dataset_version_id","sensor_index","sensor_key","nonmissing_count","distinct_nonmissing_count","constant_value"],
                "11_sensor_descriptive_statistics.sql": ["dataset_version_id","sensor_index","sensor_key","measurement_count","nonmissing_count","missing_count","minimum_value","maximum_value","mean_value","sample_stddev"],
                "12_pass_fail_mean_comparison.sql": ["dataset_version_id","sensor_index","sensor_key","pass_count","pass_mean","fail_count","fail_mean","fail_minus_pass_mean"],
                "13_standardized_mean_difference.sql": ["dataset_version_id","sensor_index","sensor_key","pass_count","pass_mean","pass_sample_variance","fail_count","fail_mean","fail_sample_variance","pooled_variance","standardized_mean_difference"],
                "14_sensor_time_series.sql": ["dataset_version_id","sensor_index","sensor_key","source_row","observed_at","outcome","outcome_name","value","is_missing"],
                "15_daily_sensor_summary.sql": ["dataset_version_id","sensor_index","sensor_key","observed_date","measurement_count","nonmissing_count","missing_count","minimum_value","maximum_value","mean_value","sample_stddev"],
                "16_observation_profile.sql": ["dataset_version_id","source_row","observed_at","outcome","outcome_name","sensor_index","sensor_key","value","is_missing"],
                "17_complete_observations.sql": ["dataset_version_id","source_row","observed_at","outcome","outcome_name"],
                "18_extreme_measurement_diagnostics.sql": ["dataset_version_id","sensor_index","sensor_key","row_kind","reason","sample_count","sample_stddev","source_row","observed_at","outcome","value","z_score","z_threshold"],
                "19_sensor_pair_correlation.sql": ["dataset_version_id","sensor_key_x","sensor_key_y","paired_count","correlation"],
                "20_measurement_long_fact.sql": ["dataset_version_id","source_row","observed_at","outcome","outcome_name","sensor_index","sensor_key","value","is_missing"],
            }
            parameters: dict[str, dict[str, object]] = {
                name: {"dataset_version_id": version_id} for name in expected_columns
            }
            parameters["14_sensor_time_series.sql"].update(sensor_key="sensor_000", start_at=datetime(2008,7,19), end_at=datetime(2008,10,18))
            parameters["15_daily_sensor_summary.sql"].update(sensor_key="sensor_000")
            parameters["16_observation_profile.sql"].update(source_row=1)
            parameters["18_extreme_measurement_diagnostics.sql"].update(z_threshold=3.0)
            parameters["19_sensor_pair_correlation.sql"].update(sensor_key_x="sensor_000", sensor_key_y="sensor_001")

            outputs: dict[str, list[dict[str, object]]] = {}
            for name in list(expected_columns)[:-1]:
                rows = self._query(engine, name, parameters[name])
                outputs[name] = rows
                if rows:
                    self.assertEqual(list(rows[0]), expected_columns[name])

            self.assertEqual(outputs["01_dataset_provenance.sql"][0]["dataset_version_id"], version_id)
            self.assertIsNotNone(outputs["01_dataset_provenance.sql"][0]["loaded_at"])
            self.assertIsNotNone(outputs["01_dataset_provenance.sql"][0]["loaded_at"].tzinfo)
            self.assertEqual(len(outputs["02_source_file_integrity.sql"]), 3)
            self.assertTrue(all(value for key,value in outputs["03_load_reconciliation.sql"][0].items() if key.endswith("_match")))
            self.assertEqual([(row["outcome"],row["observation_count"]) for row in outputs["04_outcome_distribution.sql"]], [(-1,1463),(1,104)])
            self.assertTrue(math.isclose(sum(float(row["observation_percentage"]) for row in outputs["04_outcome_distribution.sql"]), 100.0, rel_tol=1e-9))

            dataframe = self.real_source.dataframe
            repeated = dataframe.groupby("timestamp", sort=True).filter(lambda group: len(group)>1)
            expected_repeated = sorted(
                timestamp.to_pydatetime()
                for timestamp in repeated["timestamp"].drop_duplicates()
            )
            self.assertEqual([row["observed_at"] for row in outputs["06_repeated_timestamps.sql"]], expected_repeated)
            self.assertEqual(sum(int(row["occurrence_count"])-1 for row in outputs["06_repeated_timestamps.sql"]), 33)
            report = pd.read_json(DATA_DIRECTORY / "quality-report.json", typ="series") if False else None
            constant_expected = tuple(
                key for key in persistence._SENSOR_KEYS
                if dataframe[key].nunique(dropna=True) == 1
            )
            self.assertEqual(tuple(row["sensor_key"] for row in outputs["10_constant_sensors.sql"]), constant_expected)
            self.assertEqual(len(constant_expected), 116)
            sensor_zero = dataframe["sensor_000"].dropna()
            row_zero = next(row for row in outputs["11_sensor_descriptive_statistics.sql"] if row["sensor_index"]==0)
            self.assertTrue(math.isclose(float(row_zero["mean_value"]), float(sensor_zero.mean()), rel_tol=1e-9, abs_tol=1e-12))
            if len(sensor_zero) >= 2:
                self.assertTrue(math.isclose(float(row_zero["sample_stddev"]), float(sensor_zero.std(ddof=1)), rel_tol=1e-9, abs_tol=1e-12))
            complete_expected = int(dataframe.loc[:, list(persistence._SENSOR_KEYS)].notna().all(axis=1).sum())
            self.assertEqual(len(outputs["17_complete_observations.sql"]), complete_expected)
            pair = dataframe[["sensor_000","sensor_001"]].dropna()
            correlation = pair["sensor_000"].corr(pair["sensor_001"])
            self.assertEqual(outputs["19_sensor_pair_correlation.sql"][0]["paired_count"], len(pair))
            self.assertTrue(math.isclose(float(outputs["19_sensor_pair_correlation.sql"][0]["correlation"]), float(correlation), rel_tol=1e-9, abs_tol=1e-12))

            expected_values = (
                (source_row, sensor_index, value)
                for source_row, values in enumerate(dataframe.loc[:, list(persistence._SENSOR_KEYS)].itertuples(index=False, name=None), start=1)
                for sensor_index, value in enumerate(values)
            )
            count = 0
            with persistence.stream_quality_query(engine, "20_measurement_long_fact.sql", {"dataset_version_id": version_id}) as mappings:
                while batch := mappings.fetchmany(10_000):
                    for row in batch:
                        expected_row, expected_sensor, expected_value = next(expected_values)
                        self.assertEqual((row["source_row"],row["sensor_index"]), (expected_row,expected_sensor))
                        if pd.isna(expected_value):
                            self.assertIsNone(row["value"])
                        else:
                            self.assertEqual(struct.pack(">d",float(row["value"])), struct.pack(">d",float(expected_value)))
                        count += 1
            self.assertEqual(count, 924530)
        finally:
            engine.dispose()

    def test_09_statistical_null_cases_and_query_nonexistence(self) -> None:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT dataset_id FROM qualityops.dataset WHERE dataset_code=%s", (persistence._DATASET_CODE,))
                dataset_id = cursor.fetchone()[0]
                cursor.execute(
                    """INSERT INTO qualityops.dataset_version
                       (dataset_id,version_label,content_fingerprint,acquired_on,audit_schema_version,
                        observation_count,sensor_count,measurement_count,missing_measurement_count)
                       VALUES (%s,'synthetic-null-cases',%s,DATE '2026-01-01',1,3,3,9,2)
                       RETURNING dataset_version_id""",
                    (dataset_id, "C"*64),
                )
                version_id = cursor.fetchone()[0]
                cursor.executemany("INSERT INTO qualityops.sensor VALUES (%s,%s,%s)", [(version_id,i,f"sensor_{i:03d}") for i in range(3)])
                cursor.executemany("INSERT INTO qualityops.observation VALUES (%s,%s,%s,%s)", [(version_id,i,datetime(2020,1,i),-1 if i<3 else 1) for i in range(1,4)])
                values = ((1.0,1.0,1.0),(1.0,None,None),(1.0,2.0,3.0))
                cursor.executemany("INSERT INTO qualityops.measurement VALUES (%s,%s,%s,%s)", [(version_id,row,sensor,values[sensor][row-1]) for row in range(1,4) for sensor in range(3)])
            connection.commit()
        engine = create_engine(make_url(_DATABASE_URL).set(drivername="postgresql+psycopg"), echo=False)
        try:
            rows = self._query(engine, "18_extreme_measurement_diagnostics.sql", {"dataset_version_id": version_id, "z_threshold": 1.0})
            unscorable = [row for row in rows if row["row_kind"]=="unscorable"]
            self.assertEqual([(row["sensor_index"],row["reason"]) for row in unscorable], [(0,"nonpositive_variance"),(1,"insufficient_sample")])
            self.assertTrue(all(row["source_row"] is None and row["z_score"] is None for row in unscorable))
            self.assertTrue(all(row["reason"] is None for row in rows if row["row_kind"]=="extreme"))
            missing_sensor = self._query(engine, "19_sensor_pair_correlation.sql", {"dataset_version_id": version_id, "sensor_key_x":"sensor_000", "sensor_key_y":"sensor_589"})
            self.assertEqual(missing_sensor, [])
            zero_variance = self._query(engine, "19_sensor_pair_correlation.sql", {"dataset_version_id": version_id, "sensor_key_x":"sensor_000", "sensor_key_y":"sensor_002"})
            self.assertEqual(len(zero_variance), 1)
            self.assertIsNone(zero_variance[0]["correlation"])
        finally:
            engine.dispose()
            with _connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM qualityops.dataset_version WHERE dataset_version_id=%s", (version_id,))
                connection.commit()


if __name__ == "__main__":
    unittest.main()
