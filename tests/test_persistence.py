from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from io import StringIO
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from qualityops import SecomPersistenceResult
from qualityops.cli import main
from qualityops import persistence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_DIRECTORY = REPOSITORY_ROOT / "data" / "external" / "secom"
QUERY_DIRECTORY = REPOSITORY_ROOT / "sql" / "queries"
FINGERPRINT = "57856B2CA3ED8E782F88E6A9DEDC61623A4B370ED8442BB89B03BC3B44610BF7"


def _manifest() -> list[dict[str, object]]:
    report = json.loads(
        (DATA_DIRECTORY / "quality-report.json").read_text(encoding="utf-8")
    )
    return [
        {
            "name": name,
            "size": metadata["size_bytes"],
            "sha256": metadata["sha256_acquisition"],
        }
        for name, metadata in report["verified_files"].items()
    ]


class ResultContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = SecomPersistenceResult(
            status="loaded",
            dataset_code="uci-secom",
            version_label="uci-secom-acquisition-2026-08-10",
            content_fingerprint=FINGERPRINT,
            observation_count=1567,
            sensor_count=590,
            measurement_count=924530,
            missing_measurement_count=41951,
            pass_count=1463,
            fail_count=104,
        )

    def test_result_is_frozen_slotted_and_json_safe(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self.result.status = "already_loaded"  # type: ignore[misc]
        self.assertFalse(hasattr(self.result, "__dict__"))
        payload = self.result.to_dict()
        self.assertEqual(
            tuple(payload),
            (
                "status",
                "dataset_code",
                "version_label",
                "content_fingerprint",
                "observation_count",
                "sensor_count",
                "measurement_count",
                "missing_measurement_count",
                "pass_count",
                "fail_count",
            ),
        )
        json.dumps(payload, allow_nan=False)


class FingerprintTests(unittest.TestCase):
    def test_literal_oracle_and_input_order_independence(self) -> None:
        files = _manifest()
        self.assertEqual(persistence._canonical_content_fingerprint(files), FINGERPRINT)
        self.assertEqual(
            persistence._canonical_content_fingerprint(list(reversed(files))),
            FINGERPRINT,
        )

    def test_hash_normalization_is_canonical(self) -> None:
        files = _manifest()
        for item in files:
            item["sha256"] = f" {str(item['sha256']).lower()}\n"
        self.assertEqual(persistence._canonical_content_fingerprint(files), FINGERPRINT)

    def test_rejects_names_duplicates_sizes_hashes_unicode_and_ambiguous_fields(self) -> None:
        changes = (
            lambda files: files.pop(),
            lambda files: files.__setitem__(1, dict(files[0])),
            lambda files: files[0].__setitem__("name", "sécom.data"),
            lambda files: files[0].__setitem__("size", 0),
            lambda files: files[0].__setitem__("size", "05389983"),
            lambda files: files[0].__setitem__("sha256", "not-a-hash"),
            lambda files: files[0].__setitem__("extra", "ambiguous"),
        )
        for change in changes:
            with self.subTest(change=change):
                files = _manifest()
                change(files)
                with self.assertRaises(persistence.SecomDataIntegrityError):
                    persistence._canonical_content_fingerprint(files)

    def test_utf8_length_prefix_and_domain_separation_prevent_concatenation_ambiguity(self) -> None:
        source = inspect.getsource(persistence._canonical_content_fingerprint)
        self.assertIn('b"qualityops-secom-fingerprint-v1\\0"', source)
        self.assertIn('to_bytes(4, "big"', source)
        self.assertIn('name.encode("utf-8")', source)
        self.assertIn('b"size\\0"', source)
        self.assertIn('b"\\0sha256\\0"', source)

    def test_lock_oracles_and_fingerprint_independence(self) -> None:
        self.assertEqual(
            persistence._dataset_lock_digest("uci-secom"),
            "B6A342CE01BC619FE57FC83EF352D0109A0AD518459EDD96025E130EA0F70307",
        )
        self.assertEqual(
            persistence._dataset_lock_key("uci-secom"),
            -5286308085043011169,
        )
        self.assertNotEqual(
            persistence._dataset_lock_key("uci-secom-other"),
            persistence._dataset_lock_key("uci-secom"),
        )
        source = inspect.getsource(persistence._dataset_lock_key)
        self.assertNotIn("hash(", source)
        self.assertNotIn("content_fingerprint", source)

    def test_lock_is_stable_in_another_process(self) -> None:
        command = [
            sys.executable,
            "-c",
            (
                "from qualityops.persistence import _dataset_lock_key; "
                "print(_dataset_lock_key('uci-secom'))"
            ),
        ]
        completed = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.stdout.strip(), "-5286308085043011169")
        self.assertEqual(completed.stderr, "")


class PreconnectionTests(unittest.TestCase):
    def test_invalid_source_never_calls_psycopg_connect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.object(persistence.psycopg, "connect") as connect:
                with self.assertRaises(persistence.SecomDataIntegrityError):
                    persistence.persist_secom(temporary_directory, "postgresql://unused")
        connect.assert_not_called()

    def test_preconnection_contract_uses_report_and_exact_raw_names(self) -> None:
        source = inspect.getsource(persistence._verify_source_before_connect)
        connect_position = inspect.getsource(persistence.persist_secom).index(
            "psycopg.connect"
        )
        verify_position = inspect.getsource(persistence.persist_secom).index(
            "_verify_source_before_connect"
        )
        self.assertLess(verify_position, connect_position)
        for value in (
            "quality-report.json",
            "schema_version",
            "size_bytes",
            "sha256_acquisition",
            "label_row_count",
            "source_row_base",
        ):
            self.assertIn(value, source)


class CliPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = SecomPersistenceResult(
            "loaded",
            "uci-secom",
            "uci-secom-acquisition-2026-08-10",
            FINGERPRINT,
            1567,
            590,
            924530,
            41951,
            1463,
            104,
        )

    def _run(self, arguments: list[str], database_url: str | None = "postgresql://secret-user:secret-password@secret-host/db"):
        stdout = StringIO()
        stderr = StringIO()
        environment = {} if database_url is None else {"QUALITYOPS_DATABASE_URL": database_url}
        with patch.dict(os.environ, environment, clear=True), redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_success_is_compact_deterministic_json_on_stdout_only(self) -> None:
        with patch("qualityops.cli.persist_secom", return_value=self.result) as persist:
            code, stdout, stderr = self._run(
                ["load-secom-postgres", "--data-dir", str(DATA_DIRECTORY)]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            stdout,
            json.dumps(
                self.result.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n",
        )
        persist.assert_called_once()

    def test_argument_and_configuration_errors_have_exact_json_and_streams(self) -> None:
        code, stdout, stderr = self._run(["load-secom-postgres"])
        self.assertEqual((code, stdout), (2, ""))
        self.assertEqual(
            json.loads(stderr),
            {"error": {"code": "argument_error", "message": "Invalid command arguments."}},
        )
        self.assertNotIn("usage", stderr.lower())

        code, stdout, stderr = self._run(
            ["load-secom-postgres", "--data-dir", str(DATA_DIRECTORY)],
            database_url=None,
        )
        self.assertEqual((code, stdout), (2, ""))
        self.assertEqual(
            json.loads(stderr),
            {"error": {"code": "configuration_error", "message": "QUALITYOPS_DATABASE_URL is required."}},
        )

    def test_exception_families_map_to_exact_safe_errors(self) -> None:
        cases = (
            (persistence.SecomDataIntegrityError("secret"), "data_integrity_error", "SECOM source verification failed."),
            (persistence.SecomMigrationError("secret"), "migration_error", "PostgreSQL schema revision is not supported."),
            (persistence.SecomPersistenceConflictError("secret"), "persistence_conflict", "Persisted SECOM data conflicts with the verified source."),
            (persistence.SecomDatabaseError("secret"), "database_error", "PostgreSQL operation failed."),
            (RuntimeError("secret"), "internal_error", "SECOM persistence failed."),
        )
        for error, expected_code, expected_message in cases:
            with self.subTest(code=expected_code):
                with patch("qualityops.cli.persist_secom", side_effect=error):
                    code, stdout, stderr = self._run(
                        ["load-secom-postgres", "--data-dir", str(DATA_DIRECTORY)]
                    )
                self.assertEqual((code, stdout), (2, ""))
                self.assertEqual(
                    json.loads(stderr),
                    {"error": {"code": expected_code, "message": expected_message}},
                )
                for secret in ("secret-user", "secret-password", "secret-host", "secret"):
                    self.assertNotIn(secret, stderr)


class QueryContractTests(unittest.TestCase):
    def test_exactly_twenty_select_only_query_files(self) -> None:
        paths = sorted(QUERY_DIRECTORY.glob("*.sql"))
        self.assertEqual(len(paths), 20)
        self.assertEqual([path.name for path in paths], list(persistence._QUERY_PARAMETERS))
        for path in paths:
            sql = path.read_text(encoding="utf-8")
            self.assertIn("CAST(:dataset_version_id AS BIGINT)", sql)
            self.assertNotRegex(
                sql,
                r"(?i)\b(?:INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|COPY|MERGE)\b",
            )
            persistence._read_query(path.name)

    def test_parameter_validation_rejects_missing_extra_and_out_of_range_values(self) -> None:
        valid = {"dataset_version_id": 1}
        persistence._validate_query_parameters("01_dataset_provenance.sql", valid)
        invalid_cases = (
            {},
            {"dataset_version_id": 1, "extra": 1},
            {"dataset_version_id": True},
            {"dataset_version_id": 0},
            {"dataset_version_id": 2**63},
        )
        for parameters in invalid_cases:
            with self.subTest(parameters=parameters):
                with self.assertRaises(ValueError):
                    persistence._validate_query_parameters(
                        "01_dataset_provenance.sql", parameters
                    )

    def test_typed_query_parameters_and_time_window(self) -> None:
        parameters = {
            "dataset_version_id": 1,
            "sensor_key": "sensor_000",
            "start_at": datetime(2008, 1, 1),
            "end_at": datetime(2008, 1, 2),
        }
        persistence._validate_query_parameters("14_sensor_time_series.sql", parameters)
        invalid = dict(parameters, sensor_key="sensor_590")
        with self.assertRaises(ValueError):
            persistence._validate_query_parameters("14_sensor_time_series.sql", invalid)
        invalid = dict(parameters, start_at=datetime(2008, 1, 1, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            persistence._validate_query_parameters("14_sensor_time_series.sql", invalid)
        invalid = dict(parameters, end_at=parameters["start_at"])
        with self.assertRaises(ValueError):
            persistence._validate_query_parameters("14_sensor_time_series.sql", invalid)
        for threshold in (0, -1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                persistence._validate_query_parameters(
                    "18_extreme_measurement_diagnostics.sql",
                    {"dataset_version_id": 1, "z_threshold": threshold},
                )


class _FakeResult:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def mappings(self):
        return self

    def close(self) -> None:
        self.events.append("result.close")


class _FakeTransaction:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.is_active = True

    def rollback(self) -> None:
        self.events.append("transaction.rollback")
        self.is_active = False


class _FakeConnection:
    def __init__(self, events: list[str], already_active: bool = False) -> None:
        self.events = events
        self.already_active = already_active
        self.transaction = _FakeTransaction(events)
        self.result = _FakeResult(events)

    def in_transaction(self) -> bool:
        return self.already_active

    def execution_options(self, **options):
        self.events.append(f"options:{options}")
        return self

    def begin(self):
        self.events.append("begin")
        return self.transaction

    def execute(self, statement, parameters):
        self.events.append("execute")
        return self.result

    def close(self) -> None:
        self.events.append("connection.close")


class StreamContextTests(unittest.TestCase):
    def test_read_only_stream_lifetime_and_cleanup_order(self) -> None:
        events: list[str] = []
        connection = _FakeConnection(events)
        engine = MagicMock()
        engine.connect.return_value = connection
        with persistence.stream_quality_query(
            engine,
            "01_dataset_provenance.sql",
            {"dataset_version_id": 1},
        ) as mappings:
            self.assertIs(mappings, connection.result)
            events.append("consumer")
        self.assertIn("'postgresql_readonly': True", events[0])
        self.assertIn("'stream_results': True", events[0])
        self.assertEqual(
            events[-3:],
            ["result.close", "transaction.rollback", "connection.close"],
        )

    def test_consumer_exception_still_closes_result_rolls_back_and_closes_connection(self) -> None:
        events: list[str] = []
        connection = _FakeConnection(events)
        engine = MagicMock()
        engine.connect.return_value = connection
        with self.assertRaisesRegex(RuntimeError, "consumer"):
            with persistence.stream_quality_query(
                engine,
                "01_dataset_provenance.sql",
                {"dataset_version_id": 1},
            ):
                raise RuntimeError("consumer")
        self.assertEqual(
            events[-3:],
            ["result.close", "transaction.rollback", "connection.close"],
        )

    def test_pretransacted_connection_is_rejected_and_closed(self) -> None:
        events: list[str] = []
        connection = _FakeConnection(events, already_active=True)
        engine = MagicMock()
        engine.connect.return_value = connection
        with self.assertRaisesRegex(RuntimeError, "already"):
            with persistence.stream_quality_query(
                engine,
                "01_dataset_provenance.sql",
                {"dataset_version_id": 1},
            ):
                pass
        self.assertEqual(events, ["connection.close"])


class LoaderStructureTests(unittest.TestCase):
    def test_first_and_second_statements_are_literal_and_ordered(self) -> None:
        self.assertEqual(
            persistence._FIRST_SQL,
            "SELECT version_num\nFROM public.alembic_version\nORDER BY version_num;",
        )
        self.assertEqual(
            persistence._SECOND_SQL,
            "SELECT pg_advisory_xact_lock(%s);",
        )
        source = inspect.getsource(persistence._load_in_transaction)
        self.assertLess(source.index("cursor.execute(_FIRST_SQL)"), source.index("cursor.execute(_SECOND_SQL"))

    def test_loader_uses_one_psycopg_connection_and_no_sqlalchemy_engine(self) -> None:
        source = inspect.getsource(persistence.persist_secom)
        self.assertEqual(source.count("psycopg.connect"), 1)
        self.assertNotIn("create_engine", source)
        transaction_source = inspect.getsource(persistence._load_in_transaction)
        self.assertNotIn("create_engine", transaction_source)
        self.assertNotRegex(transaction_source, r"(?i)ON\s+CONFLICT")


if __name__ == "__main__":
    unittest.main()
