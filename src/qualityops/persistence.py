"""Transactional PostgreSQL persistence for the verified UCI SECOM dataset."""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import psycopg
from psycopg import Connection
from sqlalchemy import Engine, text
from sqlalchemy.engine import MappingResult

from qualityops.secom import audit_secom, load_secom


_DATASET_CODE = "uci-secom"
_DATASET_NAME = "SECOM"
_PUBLISHER = "UCI Machine Learning Repository"
_DOI = "10.24432/C54305"
_SOURCE_URL = "https://archive.ics.uci.edu/dataset/179/secom"
_LICENSE_SPDX = "CC-BY-4.0"
_VERSION_LABEL = "uci-secom-acquisition-2026-08-10"
_ACQUIRED_ON = date(2026, 8, 10)
_AUDIT_SCHEMA_VERSION = 1
_EXPECTED_REVISION = "0001_secom_persistence"
_EXPECTED_FINGERPRINT = (
    "57856B2CA3ED8E782F88E6A9DEDC61623A4B370ED8442BB89B03BC3B44610BF7"
)
_EXPECTED_LOCK_DIGEST = (
    "B6A342CE01BC619FE57FC83EF352D0109A0AD518459EDD96025E130EA0F70307"
)
_EXPECTED_LOCK_KEY = -5_286_308_085_043_011_169
_SOURCE_FILENAMES = ("secom.data", "secom.names", "secom_labels.data")
_FILE_ROLES = {
    "secom.data": "measurements",
    "secom.names": "metadata",
    "secom_labels.data": "labels",
}
_SENSOR_KEYS = tuple(f"sensor_{index:03d}" for index in range(590))
_QUERY_DIRECTORY = Path(__file__).resolve().parents[2] / "sql" / "queries"
_FIRST_SQL = """SELECT version_num
FROM public.alembic_version
ORDER BY version_num;"""
_SECOND_SQL = "SELECT pg_advisory_xact_lock(%s);"


class SecomDataIntegrityError(ValueError):
    """The SECOM files or their audit report violate the verified contract."""


class SecomMigrationError(RuntimeError):
    """The database is not at the one supported Alembic revision."""


class SecomPersistenceConflictError(RuntimeError):
    """Persisted data differs from the verified canonical source."""


class SecomDatabaseError(RuntimeError):
    """A PostgreSQL operation failed without exposing connection details."""


@dataclass(frozen=True, slots=True)
class SecomPersistenceResult:
    """JSON-safe outcome of a canonical SECOM persistence attempt."""

    status: Literal["loaded", "already_loaded"]
    dataset_code: str
    version_label: str
    content_fingerprint: str
    observation_count: int
    sensor_count: int
    measurement_count: int
    missing_measurement_count: int
    pass_count: int
    fail_count: int

    def to_dict(self) -> dict[str, str | int]:
        """Return exactly the stable public persistence-result fields."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class _SourceFile:
    filename: str
    role: str
    byte_size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _VerifiedSource:
    dataframe: pd.DataFrame
    files: tuple[_SourceFile, ...]
    dataset_code: str
    name: str
    publisher: str
    doi: str
    source_url: str
    license_spdx: str
    version_label: str
    acquired_on: date
    audit_schema_version: int
    content_fingerprint: str
    observation_count: int
    sensor_count: int
    measurement_count: int
    missing_measurement_count: int
    pass_count: int
    fail_count: int
    earliest_timestamp: datetime
    latest_timestamp: datetime


def _normalize_sha256(value: object) -> str:
    if not isinstance(value, str):
        raise SecomDataIntegrityError("SHA-256 values must be strings")
    normalized = value.strip().upper()
    if re.fullmatch(r"[0-9A-F]{64}", normalized) is None:
        raise SecomDataIntegrityError("SHA-256 values must be 64 hexadecimal characters")
    return normalized


def _reject_duplicate_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SecomDataIntegrityError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical_content_fingerprint(
    files: Sequence[Mapping[str, object]],
) -> str:
    """Hash an unambiguous, domain-separated source-file manifest."""

    if len(files) != 3:
        raise SecomDataIntegrityError("Fingerprint requires exactly three files")

    normalized: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    for file in files:
        if set(file) != {"name", "size", "sha256"}:
            raise SecomDataIntegrityError("Fingerprint file fields are invalid")
        name = file["name"]
        size = file["size"]
        if not isinstance(name, str) or name not in _SOURCE_FILENAMES:
            raise SecomDataIntegrityError("Fingerprint filename is invalid")
        if name in seen:
            raise SecomDataIntegrityError("Fingerprint filenames must be unique")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise SecomDataIntegrityError("Fingerprint sizes must be positive integers")
        seen.add(name)
        normalized.append((name, size, _normalize_sha256(file["sha256"])))

    if seen != set(_SOURCE_FILENAMES):
        raise SecomDataIntegrityError("Fingerprint filenames are incomplete")

    payload = bytearray(b"qualityops-secom-fingerprint-v1\0")
    for name, size, digest in sorted(normalized, key=lambda item: item[0].encode("utf-8")):
        name_bytes = name.encode("utf-8")
        payload.extend(b"name\0")
        payload.extend(len(name_bytes).to_bytes(4, "big", signed=False))
        payload.extend(name_bytes)
        payload.extend(b"size\0")
        payload.extend(str(size).encode("ascii"))
        payload.extend(b"\0sha256\0")
        payload.extend(digest.encode("ascii"))
        payload.extend(b"\0")
    return hashlib.sha256(payload).hexdigest().upper()


def _dataset_lock_digest(dataset_code: str) -> str:
    payload = b"qualityops:dataset-lock:v1\0" + dataset_code.encode("utf-8")
    return hashlib.sha256(payload).hexdigest().upper()


def _dataset_lock_key(dataset_code: str) -> int:
    first_eight = bytes.fromhex(_dataset_lock_digest(dataset_code))[:8]
    unsigned = int.from_bytes(first_eight, "big", signed=False)
    return unsigned if unsigned < 2**63 else unsigned - 2**64


def _load_json_report(report_path: Path) -> dict[str, Any]:
    try:
        report = json.loads(
            report_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_object_pairs,
        )
    except SecomDataIntegrityError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SecomDataIntegrityError("Unable to read the canonical audit report") from error
    if not isinstance(report, dict):
        raise SecomDataIntegrityError("The canonical audit report must be an object")
    return report


def _expect(mapping: Mapping[str, Any], path: str) -> Any:
    current: Any = mapping
    for component in path.split("."):
        if not isinstance(current, Mapping) or component not in current:
            raise SecomDataIntegrityError(f"Missing audit field: {path}")
        current = current[component]
    return current


def _verify_source_before_connect(data_dir: str | Path) -> _VerifiedSource:
    root = Path(data_dir)
    report_path = root / "quality-report.json"
    raw_directory = root / "raw"
    if not root.is_dir() or not raw_directory.is_dir() or not report_path.is_file():
        raise SecomDataIntegrityError("SECOM data_dir must contain quality-report.json and raw")

    raw_files = [path.name for path in raw_directory.iterdir() if path.is_file()]
    if len(raw_files) != 3 or set(raw_files) != set(_SOURCE_FILENAMES):
        raise SecomDataIntegrityError("SECOM raw files must have exactly the canonical names")

    report = _load_json_report(report_path)
    if _expect(report, "schema_version") != 1:
        raise SecomDataIntegrityError("Audit schema_version must be exactly 1")

    exact_dataset = {
        "name": _DATASET_NAME,
        "publisher": _PUBLISHER,
        "doi": _DOI,
        "source_url": _SOURCE_URL,
        "license": "CC BY 4.0",
        "retrieved_on": "2026-08-10",
    }
    for key, expected in exact_dataset.items():
        if _expect(report, f"dataset.{key}") != expected:
            raise SecomDataIntegrityError(f"Canonical dataset field differs: {key}")

    try:
        acquired_on = date.fromisoformat(str(_expect(report, "dataset.retrieved_on")))
    except ValueError as error:
        raise SecomDataIntegrityError("dataset.retrieved_on is invalid") from error
    if acquired_on != _ACQUIRED_ON:
        raise SecomDataIntegrityError("dataset.retrieved_on is not canonical")

    verified_files = _expect(report, "verified_files")
    if not isinstance(verified_files, Mapping) or set(verified_files) != set(
        _SOURCE_FILENAMES
    ):
        raise SecomDataIntegrityError("verified_files must contain exactly three names")

    source_files: list[_SourceFile] = []
    fingerprint_files: list[dict[str, object]] = []
    for filename in _SOURCE_FILENAMES:
        metadata = verified_files[filename]
        if not isinstance(metadata, Mapping) or set(metadata) != {
            "size_bytes",
            "sha256_acquisition",
        }:
            raise SecomDataIntegrityError(f"Invalid manifest fields for {filename}")
        size = metadata["size_bytes"]
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise SecomDataIntegrityError(f"Invalid size for {filename}")
        digest = _normalize_sha256(metadata["sha256_acquisition"])
        path = raw_directory / filename
        actual_size = path.stat().st_size
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        if actual_size != size or actual_digest != digest:
            raise SecomDataIntegrityError(f"Verified source differs: {filename}")
        source_files.append(_SourceFile(filename, _FILE_ROLES[filename], size, digest))
        fingerprint_files.append({"name": filename, "size": size, "sha256": digest})

    fingerprint = _canonical_content_fingerprint(fingerprint_files)
    if fingerprint != _EXPECTED_FINGERPRINT:
        raise SecomDataIntegrityError("Canonical SECOM fingerprint oracle differs")
    if _dataset_lock_digest(_DATASET_CODE) != _EXPECTED_LOCK_DIGEST:
        raise SecomDataIntegrityError("Canonical dataset lock digest oracle differs")
    if _dataset_lock_key(_DATASET_CODE) != _EXPECTED_LOCK_KEY:
        raise SecomDataIntegrityError("Canonical dataset lock key oracle differs")

    try:
        audit = audit_secom(raw_directory)
        regenerated_report = audit.to_dict()
        dataframe = load_secom(raw_directory)
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        raise SecomDataIntegrityError("Verified SECOM parsing failed") from error
    if regenerated_report != report:
        raise SecomDataIntegrityError("Canonical audit report differs from regenerated output")

    oracles = {
        "structure.row_count": 1_567,
        "structure.sensor_count": 590,
        "structure.label_row_count": 1_567,
        "structure.source_row_base": 1,
        "quality.missing_cell_count": 41_951,
        "quality.sensors_with_missing_count": 538,
        "quality.all_missing_sensor_count": 0,
        "quality.constant_sensor_count": 116,
        "quality.labels.pass_count": 1_463,
        "quality.labels.fail_count": 104,
        "quality.timestamps.invalid_count": 0,
        "quality.timestamps.earliest": "2008-07-19T11:55:00",
        "quality.timestamps.latest": "2008-10-17T06:07:00",
        "quality.timestamps.duplicate_occurrences_after_first": 33,
        "quality.timestamps.distinct_values_repeated": 32,
        "quality.duplicate_records.occurrences_after_first": 0,
    }
    for path, expected in oracles.items():
        if _expect(report, path) != expected:
            raise SecomDataIntegrityError(f"SECOM oracle differs: {path}")

    measurement_count = 1_567 * 590
    measurements = dataframe.loc[:, list(_SENSOR_KEYS)]
    if dataframe.shape != (1_567, 593) or measurement_count != 924_530:
        raise SecomDataIntegrityError("SECOM parsed dimensions differ")
    if int(measurements.isna().sum().sum()) != 41_951:
        raise SecomDataIntegrityError("SECOM parsed missing count differs")

    return _VerifiedSource(
        dataframe=dataframe,
        files=tuple(source_files),
        dataset_code=_DATASET_CODE,
        name=str(_expect(report, "dataset.name")),
        publisher=str(_expect(report, "dataset.publisher")),
        doi=str(_expect(report, "dataset.doi")),
        source_url=str(_expect(report, "dataset.source_url")),
        license_spdx=_LICENSE_SPDX,
        version_label=_VERSION_LABEL,
        acquired_on=acquired_on,
        audit_schema_version=int(_expect(report, "schema_version")),
        content_fingerprint=fingerprint,
        observation_count=1_567,
        sensor_count=590,
        measurement_count=measurement_count,
        missing_measurement_count=41_951,
        pass_count=1_463,
        fail_count=104,
        earliest_timestamp=datetime.fromisoformat("2008-07-19T11:55:00"),
        latest_timestamp=datetime.fromisoformat("2008-10-17T06:07:00"),
    )


def _business_result(status: Literal["loaded", "already_loaded"], source: _VerifiedSource) -> SecomPersistenceResult:
    return SecomPersistenceResult(
        status=status,
        dataset_code=source.dataset_code,
        version_label=source.version_label,
        content_fingerprint=source.content_fingerprint,
        observation_count=source.observation_count,
        sensor_count=source.sensor_count,
        measurement_count=source.measurement_count,
        missing_measurement_count=source.missing_measurement_count,
        pass_count=source.pass_count,
        fail_count=source.fail_count,
    )


def _conflict(message: str) -> None:
    raise SecomPersistenceConflictError(message)


def _fetch_unique(cursor: psycopg.Cursor[Any], sql: str, parameter: object) -> tuple[Any, ...] | None:
    cursor.execute(sql, (parameter,))
    rows = cursor.fetchall()
    if len(rows) > 1:
        _conflict("Canonical identity resolves to multiple persisted rows")
    return rows[0] if rows else None


def _validate_dataset_row(row: tuple[Any, ...], source: _VerifiedSource) -> None:
    expected = (
        source.dataset_code,
        source.name,
        source.publisher,
        source.doi,
        source.source_url,
        source.license_spdx,
    )
    if tuple(row[1:]) != expected:
        _conflict("Persisted dataset metadata differs")


def _same_float(expected: float, actual: float) -> bool:
    return struct.pack(">d", float(expected)) == struct.pack(">d", float(actual))


def _validate_persisted_version(
    connection: Connection[Any],
    dataset_row: tuple[Any, ...],
    version_row: tuple[Any, ...],
    source: _VerifiedSource,
) -> None:
    dataset_id = dataset_row[0]
    version_id = version_row[0]
    _validate_dataset_row(dataset_row, source)
    if version_row[1] != dataset_id:
        _conflict("Persisted dataset_version relation differs")
    loaded_at = version_row[5]
    if not isinstance(loaded_at, datetime) or loaded_at.tzinfo is None or loaded_at.utcoffset() is None:
        _conflict("Persisted loaded_at is invalid")
    expected_version = (
        source.version_label,
        source.content_fingerprint,
        source.acquired_on,
        source.audit_schema_version,
        source.observation_count,
        source.sensor_count,
        source.measurement_count,
        source.missing_measurement_count,
    )
    actual_version = (
        version_row[2], version_row[3], version_row[4], version_row[6],
        version_row[7], version_row[8], version_row[9], version_row[10],
    )
    if actual_version != expected_version:
        _conflict("Persisted dataset_version metadata differs")

    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT filename, role, byte_size, sha256
               FROM qualityops.source_file
               WHERE dataset_version_id = %s
               ORDER BY filename""",
            (version_id,),
        )
        expected_files = [
            (item.filename, item.role, item.byte_size, item.sha256)
            for item in source.files
        ]
        if cursor.fetchall() != expected_files:
            _conflict("Persisted source_file rows differ")

        cursor.execute(
            """SELECT sensor_index, sensor_key
               FROM qualityops.sensor
               WHERE dataset_version_id = %s
               ORDER BY sensor_index""",
            (version_id,),
        )
        expected_sensors = [(index, key) for index, key in enumerate(_SENSOR_KEYS)]
        if cursor.fetchall() != expected_sensors:
            _conflict("Persisted sensor rows differ")

        cursor.execute(
            """SELECT outcome, COUNT(*)
               FROM qualityops.observation
               WHERE dataset_version_id = %s
               GROUP BY outcome
               ORDER BY outcome""",
            (version_id,),
        )
        if cursor.fetchall() != [(-1, source.pass_count), (1, source.fail_count)]:
            _conflict("Persisted outcome counts differ")

        cursor.execute(
            """SELECT COUNT(*), MIN(observed_at), MAX(observed_at)
               FROM qualityops.observation
               WHERE dataset_version_id = %s""",
            (version_id,),
        )
        if cursor.fetchone() != (
            source.observation_count,
            source.earliest_timestamp,
            source.latest_timestamp,
        ):
            _conflict("Persisted observation counts or timestamp extremes differ")

        cursor.execute(
            """SELECT COUNT(*), COUNT(*) FILTER (WHERE value IS NULL)
               FROM qualityops.measurement
               WHERE dataset_version_id = %s""",
            (version_id,),
        )
        if cursor.fetchone() != (
            source.measurement_count,
            source.missing_measurement_count,
        ):
            _conflict("Persisted measurement counts differ")

        cursor.execute(
            """SELECT COUNT(*)
               FROM (
                   SELECT source_row
                   FROM qualityops.measurement
                   WHERE dataset_version_id = %s
                   GROUP BY source_row
                   HAVING COUNT(*) <> 590
               ) AS invalid_observation""",
            (version_id,),
        )
        if cursor.fetchone() != (0,):
            _conflict("Persisted observations do not each have 590 measurements")

    expected_observations = (
        (int(row.source_row), row.timestamp.to_pydatetime(), int(row.label))
        for row in source.dataframe.loc[:, ["source_row", "timestamp", "label"]].itertuples(index=False)
    )
    with connection.cursor(name="qualityops_validate_observations") as cursor:
        cursor.execute(
            """SELECT source_row, observed_at, outcome
               FROM qualityops.observation
               WHERE dataset_version_id = %s
               ORDER BY source_row""",
            (version_id,),
        )
        cursor.itersize = 1_000
        expected_iterator = iter(expected_observations)
        while batch := cursor.fetchmany(1_000):
            for actual in batch:
                try:
                    expected = next(expected_iterator)
                except StopIteration:
                    _conflict("Persisted observation rows contain extras")
                if actual != expected:
                    _conflict("Persisted observation content differs")
        try:
            next(expected_iterator)
        except StopIteration:
            pass
        else:
            _conflict("Persisted observation rows are missing")

    expected_measurements = (
        (source_row, sensor_index, value)
        for source_row, values in enumerate(
            source.dataframe.loc[:, list(_SENSOR_KEYS)].itertuples(index=False, name=None),
            start=1,
        )
        for sensor_index, value in enumerate(values)
    )
    with connection.cursor(name="qualityops_validate_measurements") as cursor:
        cursor.execute(
            """SELECT source_row, sensor_index, value
               FROM qualityops.measurement
               WHERE dataset_version_id = %s
               ORDER BY source_row, sensor_index""",
            (version_id,),
        )
        cursor.itersize = 10_000
        expected_iterator = iter(expected_measurements)
        while batch := cursor.fetchmany(10_000):
            for actual in batch:
                try:
                    expected_row, expected_sensor, expected_value = next(
                        expected_iterator
                    )
                except StopIteration:
                    _conflict("Persisted measurement rows contain extras")
                if actual[0] != expected_row or actual[1] != expected_sensor:
                    _conflict("Persisted measurement coordinates differ")
                actual_value = actual[2]
                if pd.isna(expected_value):
                    if actual_value is not None:
                        _conflict("Persisted measurement NULL state differs")
                elif actual_value is None or not _same_float(
                    float(expected_value), actual_value
                ):
                    _conflict("Persisted measurement value differs")
        try:
            next(expected_iterator)
        except StopIteration:
            pass
        else:
            _conflict("Persisted measurement rows are missing")


def _insert_source(connection: Connection[Any], dataset_id: int, source: _VerifiedSource) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO qualityops.dataset_version (
                   dataset_id, version_label, content_fingerprint, acquired_on,
                   audit_schema_version, observation_count, sensor_count,
                   measurement_count, missing_measurement_count
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING dataset_version_id""",
            (
                dataset_id, source.version_label, source.content_fingerprint, source.acquired_on,
                source.audit_schema_version, source.observation_count, source.sensor_count,
                source.measurement_count, source.missing_measurement_count,
            ),
        )
        version_id = cursor.fetchone()[0]
        cursor.executemany(
            """INSERT INTO qualityops.source_file
               (dataset_version_id, filename, role, byte_size, sha256)
               VALUES (%s, %s, %s, %s, %s)""",
            [
                (version_id, item.filename, item.role, item.byte_size, item.sha256)
                for item in source.files
            ],
        )
        cursor.executemany(
            """INSERT INTO qualityops.sensor
               (dataset_version_id, sensor_index, sensor_key)
               VALUES (%s, %s, %s)""",
            [(version_id, index, key) for index, key in enumerate(_SENSOR_KEYS)],
        )
        cursor.executemany(
            """INSERT INTO qualityops.observation
               (dataset_version_id, source_row, observed_at, outcome)
               VALUES (%s, %s, %s, %s)""",
            [
                (
                    version_id,
                    int(row.source_row),
                    row.timestamp.to_pydatetime(),
                    int(row.label),
                )
                for row in source.dataframe.loc[:, ["source_row", "timestamp", "label"]].itertuples(index=False)
            ],
        )
        with cursor.copy(
            """COPY qualityops.measurement
               (dataset_version_id, source_row, sensor_index, value)
               FROM STDIN"""
        ) as copy:
            for source_row, values in enumerate(
                source.dataframe.loc[:, list(_SENSOR_KEYS)].itertuples(index=False, name=None),
                start=1,
            ):
                for sensor_index, value in enumerate(values):
                    copy.write_row(
                        (
                            version_id,
                            source_row,
                            sensor_index,
                            None if pd.isna(value) else float(value),
                        )
                    )
    return version_id


def _load_in_transaction(connection: Connection[Any], source: _VerifiedSource) -> SecomPersistenceResult:
    with connection.cursor() as cursor:
        try:
            cursor.execute(_FIRST_SQL)
            revisions = [row[0] for row in cursor.fetchall()]
        except psycopg.Error as error:
            raise SecomMigrationError("Unsupported Alembic revision") from error
        if revisions != [_EXPECTED_REVISION]:
            raise SecomMigrationError("Unsupported Alembic revision")

        cursor.execute(_SECOND_SQL, (_dataset_lock_key(source.dataset_code),))

        dataset_row = _fetch_unique(
            cursor,
            """SELECT dataset_id, dataset_code, name, publisher, doi, source_url, license_spdx
               FROM qualityops.dataset WHERE dataset_code = %s""",
            source.dataset_code,
        )
        label_row = _fetch_unique(
            cursor,
            """SELECT dataset_version_id, dataset_id, version_label, content_fingerprint,
                      acquired_on, loaded_at, audit_schema_version, observation_count,
                      sensor_count, measurement_count, missing_measurement_count
               FROM qualityops.dataset_version WHERE version_label = %s""",
            source.version_label,
        )
        fingerprint_row = _fetch_unique(
            cursor,
            """SELECT dataset_version_id, dataset_id, version_label, content_fingerprint,
                      acquired_on, loaded_at, audit_schema_version, observation_count,
                      sensor_count, measurement_count, missing_measurement_count
               FROM qualityops.dataset_version WHERE content_fingerprint = %s""",
            source.content_fingerprint,
        )

        if dataset_row is not None:
            _validate_dataset_row(dataset_row, source)
        if (label_row is None) != (fingerprint_row is None):
            _conflict("Canonical label and fingerprint resolve inconsistently")
        if label_row is not None and fingerprint_row is not None:
            if label_row[0] != fingerprint_row[0] or label_row != fingerprint_row:
                _conflict("Canonical label and fingerprint resolve to different versions")
            if dataset_row is None or label_row[1] != dataset_row[0]:
                _conflict("Canonical version is associated with another dataset")
            _validate_persisted_version(connection, dataset_row, label_row, source)
            return _business_result("already_loaded", source)
        if dataset_row is None and (label_row is not None or fingerprint_row is not None):
            _conflict("Canonical version exists without the canonical dataset")

        if dataset_row is None:
            cursor.execute(
                """INSERT INTO qualityops.dataset
                   (dataset_code, name, publisher, doi, source_url, license_spdx)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING dataset_id""",
                (
                    source.dataset_code,
                    source.name,
                    source.publisher,
                    source.doi,
                    source.source_url,
                    source.license_spdx,
                ),
            )
            dataset_id = cursor.fetchone()[0]
        else:
            dataset_id = dataset_row[0]

    version_id = _insert_source(connection, dataset_id, source)
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT dataset_id, dataset_code, name, publisher, doi, source_url, license_spdx
               FROM qualityops.dataset WHERE dataset_id = %s""",
            (dataset_id,),
        )
        inserted_dataset = cursor.fetchone()
        cursor.execute(
            """SELECT dataset_version_id, dataset_id, version_label, content_fingerprint,
                      acquired_on, loaded_at, audit_schema_version, observation_count,
                      sensor_count, measurement_count, missing_measurement_count
               FROM qualityops.dataset_version WHERE dataset_version_id = %s""",
            (version_id,),
        )
        inserted_version = cursor.fetchone()
    _validate_persisted_version(connection, inserted_dataset, inserted_version, source)
    return _business_result("loaded", source)


def persist_secom(data_dir: str | Path, database_url: str) -> SecomPersistenceResult:
    """Verify and persist canonical SECOM data in one Psycopg transaction."""

    source = _verify_source_before_connect(data_dir)
    connection: Connection[Any] | None = None
    try:
        connection = psycopg.connect(
            database_url,
            autocommit=False,
            application_name="qualityops-load-secom",
        )
        result = _load_in_transaction(connection, source)
        connection.commit()
        return result
    except (SecomMigrationError, SecomPersistenceConflictError):
        if connection is not None:
            connection.rollback()
        raise
    except psycopg.Error as error:
        if connection is not None:
            connection.rollback()
        raise SecomDatabaseError("PostgreSQL operation failed") from error
    except Exception:
        if connection is not None:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()


_QUERY_PARAMETERS: dict[str, dict[str, str]] = {
    "01_dataset_provenance.sql": {"dataset_version_id": "bigint"},
    "02_source_file_integrity.sql": {"dataset_version_id": "bigint"},
    "03_load_reconciliation.sql": {"dataset_version_id": "bigint"},
    "04_outcome_distribution.sql": {"dataset_version_id": "bigint"},
    "05_daily_yield.sql": {"dataset_version_id": "bigint"},
    "06_repeated_timestamps.sql": {"dataset_version_id": "bigint"},
    "07_sensor_missingness.sql": {"dataset_version_id": "bigint"},
    "08_observation_missingness.sql": {"dataset_version_id": "bigint"},
    "09_sensor_missingness_by_outcome.sql": {"dataset_version_id": "bigint"},
    "10_constant_sensors.sql": {"dataset_version_id": "bigint"},
    "11_sensor_descriptive_statistics.sql": {"dataset_version_id": "bigint"},
    "12_pass_fail_mean_comparison.sql": {"dataset_version_id": "bigint"},
    "13_standardized_mean_difference.sql": {"dataset_version_id": "bigint"},
    "14_sensor_time_series.sql": {
        "dataset_version_id": "bigint", "sensor_key": "sensor_key",
        "start_at": "start_at", "end_at": "end_at",
    },
    "15_daily_sensor_summary.sql": {"dataset_version_id": "bigint", "sensor_key": "sensor_key"},
    "16_observation_profile.sql": {"dataset_version_id": "bigint", "source_row": "integer"},
    "17_complete_observations.sql": {"dataset_version_id": "bigint"},
    "18_extreme_measurement_diagnostics.sql": {"dataset_version_id": "bigint", "z_threshold": "positive_float"},
    "19_sensor_pair_correlation.sql": {
        "dataset_version_id": "bigint", "sensor_key_x": "sensor_key", "sensor_key_y": "sensor_key",
    },
    "20_measurement_long_fact.sql": {"dataset_version_id": "bigint"},
}


def _validate_query_parameters(query_name: str, parameters: Mapping[str, object]) -> None:
    if query_name not in _QUERY_PARAMETERS:
        raise ValueError("Query name is not in the audited allowlist")
    expected = _QUERY_PARAMETERS[query_name]
    if set(parameters) != set(expected):
        raise ValueError("Query parameters must match the exact contract")
    for name, kind in expected.items():
        value = parameters[name]
        if kind == "bigint":
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 9_223_372_036_854_775_807:
                raise ValueError(f"{name} must be a positive BIGINT")
        elif kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 2_147_483_647:
                raise ValueError(f"{name} must be a positive INTEGER")
        elif kind == "sensor_key":
            if not isinstance(value, str) or value not in _SENSOR_KEYS:
                raise ValueError(f"{name} must be sensor_000 through sensor_589")
        elif kind in {"start_at", "end_at"}:
            if not isinstance(value, datetime) or value.tzinfo is not None:
                raise ValueError(f"{name} must be a naive datetime")
        elif kind == "positive_float":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"{name} must be finite and positive")
    if "start_at" in parameters and parameters["start_at"] >= parameters["end_at"]:  # type: ignore[operator]
        raise ValueError("start_at must be earlier than end_at")


def _read_query(query_name: str) -> str:
    sql = (_QUERY_DIRECTORY / query_name).read_text(encoding="utf-8")
    if re.search(r"\b(?:INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|COPY|MERGE)\b", sql, re.IGNORECASE):
        raise ValueError("Analytical SQL cannot contain DDL or DML")
    return sql


@contextmanager
def stream_quality_query(
    engine: Engine,
    query_name: str,
    parameters: Mapping[str, object],
) -> Iterator[MappingResult]:
    """Stream one allowlisted analytical query in a read-only transaction."""

    _validate_query_parameters(query_name, parameters)
    sql = _read_query(query_name)
    connection = None
    transaction = None
    result = None
    try:
        connection = engine.connect()
        if connection.in_transaction():
            raise RuntimeError("Analytical connection already has an active transaction")
        connection = connection.execution_options(
            postgresql_readonly=True,
            stream_results=True,
        )
        transaction = connection.begin()
        result = connection.execute(text(sql), dict(parameters))
        yield result.mappings()
    finally:
        if result is not None:
            result.close()
        if transaction is not None and transaction.is_active:
            transaction.rollback()
        if transaction is not None and transaction.is_active:
            raise RuntimeError("Analytical transaction remained active after rollback")
        if connection is not None:
            connection.close()
