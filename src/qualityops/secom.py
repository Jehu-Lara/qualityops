"""Verified loading and deterministic quality auditing for UCI SECOM."""

from __future__ import annotations

import hashlib
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import pandas as pd


_SENSOR_NAMES = tuple(f"sensor_{index:03d}" for index in range(590))
_SOURCE_FILENAMES = ("secom.data", "secom_labels.data", "secom.names")
_EXPECTED_FILES = {
    "secom.data": (
        5_389_983,
        "20F0E7EE434F7DCBAE0EEA9FFFF009A2B57F42D6B0DC9A5BD4F00782C0A3374C",
    ),
    "secom_labels.data": (
        40_638,
        "126884CF453705C9E61A903FE906F0665A3B45CE3639E621EDC5C93C89627E03",
    ),
    "secom.names": (
        4_223,
        "6D91B0B46CDEE03064EE3E3112F937C1B3F7FCD9933575794EC07974E6F1EA59",
    ),
}
_FORBIDDEN_ENVIRONMENT_KEYS = {
    "cwd",
    "data_dir",
    "generated_at",
    "home",
    "host",
    "hostname",
    "path",
    "platform",
    "python_version",
    "user",
    "username",
}
_ALLOWED_URL_FIELDS = {
    ("dataset", "source_url"),
    ("dataset", "download_url"),
}


@dataclass(frozen=True, slots=True)
class _SecomPaths:
    data: Path
    labels: Path
    names: Path


@dataclass(frozen=True, slots=True)
class _FileMetadata:
    filename: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SecomAuditResult:
    """Immutable, JSON-serializable SECOM data-quality audit."""

    verified_files: tuple[_FileMetadata, ...]
    row_count: int
    sensor_count: int
    label_row_count: int
    missing_cell_count: int
    sensors_with_missing_count: int
    missing_by_sensor: tuple[tuple[str, int], ...]
    all_missing_sensors: tuple[str, ...]
    constant_sensors: tuple[str, ...]
    duplicate_record_count: int
    pass_count: int
    fail_count: int
    unexpected_label_count: int
    invalid_timestamp_count: int
    earliest_timestamp: str
    latest_timestamp: str
    duplicate_timestamp_occurrences: int
    distinct_repeated_timestamps: int

    def __post_init__(self) -> None:
        sensor_names = tuple(name for name, _ in self.missing_by_sensor)
        missing_counts = tuple(count for _, count in self.missing_by_sensor)
        file_names = tuple(file.filename for file in self.verified_files)

        if self.sensor_count != len(_SENSOR_NAMES):
            raise ValueError("SECOM audit must report exactly 590 sensors")
        if sensor_names != _SENSOR_NAMES:
            raise ValueError("SECOM missing-value keys must contain every sensor in order")
        if any(count < 0 for count in missing_counts):
            raise ValueError("SECOM missing-value counts cannot be negative")
        if sum(missing_counts) != self.missing_cell_count:
            raise ValueError("SECOM missing-value totals are inconsistent")
        if sum(count > 0 for count in missing_counts) != self.sensors_with_missing_count:
            raise ValueError("SECOM sensors-with-missing count is inconsistent")
        if len(self.all_missing_sensors) != len(set(self.all_missing_sensors)):
            raise ValueError("SECOM all-missing sensor list contains duplicates")
        if len(self.constant_sensors) != len(set(self.constant_sensors)):
            raise ValueError("SECOM constant sensor list contains duplicates")
        if not set(self.all_missing_sensors).issubset(_SENSOR_NAMES):
            raise ValueError("SECOM all-missing sensor list contains unknown sensors")
        if not set(self.constant_sensors).issubset(_SENSOR_NAMES):
            raise ValueError("SECOM constant sensor list contains unknown sensors")
        if tuple(sorted(self.all_missing_sensors)) != self.all_missing_sensors:
            raise ValueError("SECOM all-missing sensors must be ordered")
        if tuple(sorted(self.constant_sensors)) != self.constant_sensors:
            raise ValueError("SECOM constant sensors must be ordered")
        if self.pass_count + self.fail_count + self.unexpected_label_count != self.row_count:
            raise ValueError("SECOM label counts are inconsistent with row count")
        if self.label_row_count != self.row_count:
            raise ValueError("SECOM label and measurement row counts are inconsistent")
        if self.duplicate_record_count < 0:
            raise ValueError("SECOM duplicate record count cannot be negative")
        if self.invalid_timestamp_count < 0:
            raise ValueError("SECOM invalid timestamp count cannot be negative")
        if self.duplicate_timestamp_occurrences < self.distinct_repeated_timestamps:
            raise ValueError("SECOM duplicate timestamp counts are inconsistent")
        if file_names != _SOURCE_FILENAMES:
            raise ValueError("SECOM audit must contain exactly the three source files")

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh dictionary matching the stable public JSON contract."""

        report: dict[str, Any] = {
            "schema_version": 1,
            "dataset": {
                "name": "SECOM",
                "publisher": "UCI Machine Learning Repository",
                "creators": ["Michael McCann", "Adrian Johnston"],
                "doi": "10.24432/C54305",
                "license": "CC BY 4.0",
                "source_url": "https://archive.ics.uci.edu/dataset/179/secom",
                "download_url": (
                    "https://archive.ics.uci.edu/static/public/179/secom.zip"
                ),
                "retrieved_on": "2026-08-10",
                "archive_acquisition_record": {
                    "filename": "secom.zip",
                    "size_bytes": 1_964_989,
                    "sha256_acquisition": (
                        "EEA568BAF3C2229096D7D294CF0B096B5502BD96D92C0B80A65B84714059BE8E"
                    ),
                    "committed": False,
                    "verified_by_cli": False,
                },
            },
            "verified_files": {
                file.filename: {
                    "size_bytes": file.size_bytes,
                    "sha256_acquisition": file.sha256,
                }
                for file in self.verified_files
            },
            "structure": {
                "row_count": self.row_count,
                "sensor_count": self.sensor_count,
                "label_row_count": self.label_row_count,
                "source_row_base": 1,
            },
            "quality": {
                "missing_cell_count": self.missing_cell_count,
                "sensors_with_missing_count": self.sensors_with_missing_count,
                "missing_by_sensor": dict(self.missing_by_sensor),
                "all_missing_sensor_count": len(self.all_missing_sensors),
                "all_missing_sensors": list(self.all_missing_sensors),
                "constant_sensor_count": len(self.constant_sensors),
                "constant_sensors": list(self.constant_sensors),
                "duplicate_records": {
                    "comparison_columns": [
                        "timestamp",
                        "label",
                        *_SENSOR_NAMES,
                    ],
                    "comparison_excludes": ["source_row"],
                    "nan_values_compare_equal": True,
                    "occurrences_after_first": self.duplicate_record_count,
                },
                "labels": {
                    "pass_value": -1,
                    "fail_value": 1,
                    "pass_count": self.pass_count,
                    "fail_count": self.fail_count,
                    "unexpected_count": self.unexpected_label_count,
                },
                "timestamps": {
                    "invalid_count": self.invalid_timestamp_count,
                    "earliest": self.earliest_timestamp,
                    "latest": self.latest_timestamp,
                    "duplicate_occurrences_after_first": (
                        self.duplicate_timestamp_occurrences
                    ),
                    "distinct_values_repeated": self.distinct_repeated_timestamps,
                },
            },
        }
        _validate_report_contract(report)
        _validate_portable_json(report)
        return report


def _normalize_sha256(value: str) -> str:
    normalized = value.strip().upper()
    if re.fullmatch(r"[0-9A-F]{64}", normalized) is None:
        raise ValueError("SHA-256 values must contain exactly 64 hexadecimal characters")
    return normalized


def _resolve_secom_paths(data_dir: str | Path) -> _SecomPaths:
    directory = Path(data_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"SECOM data directory not found: {directory}")

    paths = _SecomPaths(
        data=directory / "secom.data",
        labels=directory / "secom_labels.data",
        names=directory / "secom.names",
    )
    for path in (paths.data, paths.labels, paths.names):
        if not path.is_file():
            raise FileNotFoundError(f"Required SECOM file not found: {path.name}")
    return paths


def _compute_file_metadata(paths: _SecomPaths) -> tuple[_FileMetadata, ...]:
    metadata = []
    for path in (paths.data, paths.labels, paths.names):
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        metadata.append(
            _FileMetadata(
                filename=path.name,
                size_bytes=path.stat().st_size,
                sha256=digest,
            )
        )
    return tuple(metadata)


def _verify_secom_hashes(metadata: tuple[_FileMetadata, ...]) -> None:
    if tuple(file.filename for file in metadata) != _SOURCE_FILENAMES:
        raise ValueError("SECOM integrity check requires exactly the three source files")

    for file in metadata:
        expected_size, expected_hash = _EXPECTED_FILES[file.filename]
        if file.size_bytes != expected_size:
            raise ValueError(
                f"Unexpected size for {file.filename}: "
                f"expected {expected_size}, got {file.size_bytes}"
            )
        if _normalize_sha256(file.sha256) != _normalize_sha256(expected_hash):
            raise ValueError(f"SHA-256 mismatch for {file.filename}")


def _parse_secom_files(paths: _SecomPaths) -> pd.DataFrame:
    try:
        measurements = pd.read_csv(
            paths.data,
            sep=r"\s+",
            header=None,
            na_values="NaN",
        )
        labels = pd.read_csv(
            paths.labels,
            sep=r"\s+",
            header=None,
            names=["label", "timestamp"],
        )
    except (OSError, pd.errors.ParserError) as error:
        raise ValueError(f"Unable to parse SECOM source files: {error}") from error

    measurements.columns = [
        f"sensor_{index:03d}" for index in range(len(measurements.columns))
    ]
    numeric_labels = pd.to_numeric(labels["label"], errors="coerce")
    timestamps = pd.to_datetime(
        labels["timestamp"],
        format="%d/%m/%Y %H:%M:%S",
        errors="coerce",
    )

    header = pd.DataFrame(
        {
            "source_row": range(1, len(measurements) + 1),
            "timestamp": timestamps,
            "label": numeric_labels,
        }
    )
    return pd.concat(
        [header.reset_index(drop=True), measurements.reset_index(drop=True)],
        axis=1,
    )


def _validate_secom_invariants(dataframe: pd.DataFrame) -> None:
    expected_columns = ("source_row", "timestamp", "label", *_SENSOR_NAMES)
    if tuple(dataframe.columns) != expected_columns:
        raise ValueError("SECOM data must contain metadata plus exactly 590 sensors")
    if len(dataframe) != 1_567:
        raise ValueError("SECOM data must contain exactly 1567 aligned rows")
    if tuple(dataframe["source_row"]) != tuple(range(1, 1_568)):
        raise ValueError("SECOM source_row must be 1-based and contiguous")
    if dataframe["label"].isna().any():
        raise ValueError("SECOM labels must be numeric")
    if not set(dataframe["label"].astype(int).unique()).issubset({-1, 1}):
        raise ValueError("SECOM labels must contain only -1 and 1")
    if dataframe["timestamp"].isna().any():
        raise ValueError("SECOM timestamps must use DD/MM/YYYY HH:MM:SS format")


def _validate_exact_keys(
    mapping: dict[str, Any], expected: set[str], context: str
) -> None:
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        additional = sorted(actual - expected)
        raise ValueError(
            f"Invalid {context} keys; missing={missing}, additional={additional}"
        )


def _validate_report_contract(report: dict[str, Any]) -> None:
    _validate_exact_keys(
        report,
        {"schema_version", "dataset", "verified_files", "structure", "quality"},
        "report",
    )
    _validate_exact_keys(
        report["dataset"],
        {
            "name",
            "publisher",
            "creators",
            "doi",
            "license",
            "source_url",
            "download_url",
            "retrieved_on",
            "archive_acquisition_record",
        },
        "dataset",
    )
    _validate_exact_keys(
        report["dataset"]["archive_acquisition_record"],
        {
            "filename",
            "size_bytes",
            "sha256_acquisition",
            "committed",
            "verified_by_cli",
        },
        "archive acquisition record",
    )
    _validate_exact_keys(report["verified_files"], set(_SOURCE_FILENAMES), "files")
    for filename, metadata in report["verified_files"].items():
        _validate_exact_keys(
            metadata,
            {"size_bytes", "sha256_acquisition"},
            f"{filename} metadata",
        )
    _validate_exact_keys(
        report["structure"],
        {"row_count", "sensor_count", "label_row_count", "source_row_base"},
        "structure",
    )
    _validate_exact_keys(
        report["quality"],
        {
            "missing_cell_count",
            "sensors_with_missing_count",
            "missing_by_sensor",
            "all_missing_sensor_count",
            "all_missing_sensors",
            "constant_sensor_count",
            "constant_sensors",
            "duplicate_records",
            "labels",
            "timestamps",
        },
        "quality",
    )
    _validate_exact_keys(
        report["quality"]["missing_by_sensor"], set(_SENSOR_NAMES), "sensor map"
    )
    _validate_exact_keys(
        report["quality"]["duplicate_records"],
        {
            "comparison_columns",
            "comparison_excludes",
            "nan_values_compare_equal",
            "occurrences_after_first",
        },
        "duplicate records",
    )
    _validate_exact_keys(
        report["quality"]["labels"],
        {"pass_value", "fail_value", "pass_count", "fail_count", "unexpected_count"},
        "labels",
    )
    _validate_exact_keys(
        report["quality"]["timestamps"],
        {
            "invalid_count",
            "earliest",
            "latest",
            "duplicate_occurrences_after_first",
            "distinct_values_repeated",
        },
        "timestamps",
    )


def _validate_portable_json(value: Any, field_path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in _FORBIDDEN_ENVIRONMENT_KEYS:
                raise ValueError(f"Environment-dependent JSON field is forbidden: {key}")
            _validate_portable_json(child, (*field_path, key))
        return
    if isinstance(value, list):
        for child in value:
            _validate_portable_json(child, field_path)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON report cannot contain NaN or Infinity")
    if isinstance(value, str):
        if "://" in value:
            if field_path not in _ALLOWED_URL_FIELDS:
                raise ValueError("URLs are allowed only in documented source fields")
            return
        if PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute():
            raise ValueError("JSON report cannot contain absolute paths")


def _load_verified_secom(
    data_dir: str | Path,
) -> tuple[pd.DataFrame, tuple[_FileMetadata, ...]]:
    paths = _resolve_secom_paths(data_dir)
    metadata = _compute_file_metadata(paths)
    _verify_secom_hashes(metadata)
    dataframe = _parse_secom_files(paths)
    _validate_secom_invariants(dataframe)
    return dataframe, metadata


def _constant_sensor_names(
    dataframe: pd.DataFrame, sensor_names: tuple[str, ...]
) -> tuple[str, ...]:
    return tuple(
        sensor
        for sensor in sensor_names
        if int(dataframe[sensor].nunique(dropna=True)) == 1
    )


def _count_duplicate_records(
    dataframe: pd.DataFrame, sensor_names: tuple[str, ...]
) -> int:
    seen: set[tuple[Any, ...]] = set()
    duplicate_count = 0

    for row in dataframe.loc[:, ["timestamp", "label", *sensor_names]].itertuples(
        index=False, name=None
    ):
        timestamp, label, *values = row
        measurement_key = tuple(
            ("missing",) if pd.isna(value) else ("value", struct.pack(">d", float(value)))
            for value in values
        )
        key = (timestamp.to_pydatetime(), int(label), *measurement_key)
        if key in seen:
            duplicate_count += 1
        else:
            seen.add(key)
    return duplicate_count


def load_secom(data_dir: str | Path) -> pd.DataFrame:
    """Load the byte-verified UCI SECOM source files into one dataframe."""

    dataframe, _ = _load_verified_secom(data_dir)
    return dataframe


def audit_secom(data_dir: str | Path) -> SecomAuditResult:
    """Return a deterministic quality audit for verified UCI SECOM files."""

    dataframe, metadata = _load_verified_secom(data_dir)
    sensors = dataframe.loc[:, list(_SENSOR_NAMES)]
    missing = sensors.isna().sum()
    missing_by_sensor = tuple(
        (sensor, int(missing[sensor])) for sensor in _SENSOR_NAMES
    )
    all_missing_sensors = tuple(
        sensor for sensor in _SENSOR_NAMES if bool(sensors[sensor].isna().all())
    )
    constant_sensors = _constant_sensor_names(sensors, _SENSOR_NAMES)
    duplicate_record_count = _count_duplicate_records(dataframe, _SENSOR_NAMES)
    label_counts = dataframe["label"].astype(int).value_counts()
    timestamps = dataframe["timestamp"]

    result = SecomAuditResult(
        verified_files=metadata,
        row_count=int(len(dataframe)),
        sensor_count=len(_SENSOR_NAMES),
        label_row_count=int(dataframe["label"].count()),
        missing_cell_count=int(missing.sum()),
        sensors_with_missing_count=int((missing > 0).sum()),
        missing_by_sensor=missing_by_sensor,
        all_missing_sensors=all_missing_sensors,
        constant_sensors=constant_sensors,
        duplicate_record_count=duplicate_record_count,
        pass_count=int(label_counts.get(-1, 0)),
        fail_count=int(label_counts.get(1, 0)),
        unexpected_label_count=int((~dataframe["label"].isin([-1, 1])).sum()),
        invalid_timestamp_count=int(timestamps.isna().sum()),
        earliest_timestamp=timestamps.min().isoformat(),
        latest_timestamp=timestamps.max().isoformat(),
        duplicate_timestamp_occurrences=int(timestamps.duplicated(keep="first").sum()),
        distinct_repeated_timestamps=int((timestamps.value_counts() > 1).sum()),
    )
    result.to_dict()
    return result
