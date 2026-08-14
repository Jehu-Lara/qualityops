"""Normalize complete Power BI DAX Results grids into reproducible TSV evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterable


INTEGER_PATTERN = re.compile(r"^-?[0-9]+$")
FLOAT_PATTERN = re.compile(
    r"^-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?$"
)
BRACKETED_HEADER_PATTERN = re.compile(r"^\[([^\[\]]+)\]$")
RFC_EN_US_PATTERN = re.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), "
    r"(0[1-9]|[12][0-9]|3[01]) "
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r"([0-9]{4}) "
    r"([01][0-9]|2[0-3]):([0-5][0-9]):([0-5][0-9])$"
)
RFC_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
RFC_MONTHS = {
    name: index
    for index, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        start=1,
    )
}

NON_NULL_BIGINT = "NON_NULL_BIGINT"
NON_NULL_TIMESTAMPTZ = "NON_NULL_TIMESTAMPTZ"
NULL = "NULL"


@dataclass(frozen=True)
class Column:
    name: str
    kind: str
    nullable: bool = False


@dataclass(frozen=True)
class ExportSchema:
    columns: tuple[Column, ...]
    row_count: int
    sort_key: Callable[[dict[str, str]], object]


def _columns(*items: tuple[str, str] | tuple[str, str, bool]) -> tuple[Column, ...]:
    return tuple(Column(*item) for item in items)


SCHEMAS: dict[str, ExportSchema] = {
    "01_dataset_provenance.tsv": ExportSchema(
        _columns(
            ("dataset_version_id", "dataset_version_id"),
            ("dataset_code", "text"),
            ("name", "text"),
            ("publisher", "text"),
            ("doi", "text", True),
            ("source_url", "text"),
            ("license_spdx", "text"),
            ("version_label", "text"),
            ("acquired_on", "date"),
            ("loaded_at", "loaded_at"),
            ("audit_schema_version", "integer"),
            ("content_fingerprint", "text"),
        ),
        1,
        lambda row: (row["dataset_version_id"],),
    ),
    "03_load_reconciliation.tsv": ExportSchema(
        _columns(
            ("dataset_version_id", "dataset_version_id"),
            ("expected_observation_count", "integer"),
            ("actual_observation_count", "integer"),
            ("observations_match", "boolean"),
            ("expected_sensor_count", "integer"),
            ("actual_sensor_count", "integer"),
            ("sensors_match", "boolean"),
            ("expected_measurement_count", "integer"),
            ("actual_measurement_count", "integer"),
            ("measurements_match", "boolean"),
            ("expected_missing_measurement_count", "integer"),
            ("actual_missing_measurement_count", "integer"),
            ("missing_measurements_match", "boolean"),
            ("measurements_per_observation_match", "boolean"),
        ),
        1,
        lambda row: (row["dataset_version_id"],),
    ),
    "04_outcome_distribution.tsv": ExportSchema(
        _columns(
            ("dataset_version_id", "dataset_version_id"),
            ("outcome", "integer"),
            ("outcome_name", "text"),
            ("observation_count", "integer"),
            ("observation_percentage", "float"),
        ),
        2,
        lambda row: int(row["outcome"]),
    ),
    "05_daily_yield.tsv": ExportSchema(
        _columns(
            ("dataset_version_id", "dataset_version_id"),
            ("observed_date", "date"),
            ("observation_count", "integer"),
            ("pass_count", "integer"),
            ("fail_count", "integer"),
            ("fail_rate", "float"),
        ),
        86,
        lambda row: row["observed_date"],
    ),
    "07_sensor_missingness.tsv": ExportSchema(
        _columns(
            ("dataset_version_id", "dataset_version_id"),
            ("sensor_index", "integer"),
            ("sensor_key", "text"),
            ("measurement_count", "integer"),
            ("nonmissing_count", "integer"),
            ("missing_count", "integer"),
            ("missing_rate", "float"),
        ),
        590,
        lambda row: int(row["sensor_index"]),
    ),
    "13_standardized_mean_difference.tsv": ExportSchema(
        _columns(
            ("dataset_version_id", "dataset_version_id"),
            ("sensor_index", "integer"),
            ("sensor_key", "text"),
            ("pass_count", "integer"),
            ("pass_mean", "float", True),
            ("pass_sample_variance", "float", True),
            ("fail_count", "integer"),
            ("fail_mean", "float", True),
            ("fail_sample_variance", "float", True),
            ("pooled_variance", "float", True),
            ("standardized_mean_difference", "float", True),
        ),
        590,
        lambda row: (
            row["standardized_mean_difference"] == NULL,
            -abs(float(row["standardized_mean_difference"]))
            if row["standardized_mean_difference"] != NULL
            else 0.0,
            int(row["sensor_index"]),
        ),
    ),
}


def _normalized_header(value: str) -> str:
    match = BRACKETED_HEADER_PATTERN.fullmatch(value)
    return match.group(1) if match else value


def _parse_rfc_en_us(value: str) -> datetime:
    match = RFC_EN_US_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("not the exact RFC en-US format")
    weekday, day, month, year, hour, minute, second = match.groups()
    parsed = datetime(
        int(year), RFC_MONTHS[month], int(day), int(hour), int(minute), int(second)
    )
    if RFC_WEEKDAYS[parsed.weekday()] != weekday:
        raise ValueError("RFC en-US weekday does not match the calendar date")
    return parsed


def _parse_date(value: str, *, filename: str, column: str) -> str:
    parsers: tuple[Callable[[str], datetime | date], ...] = (
        date.fromisoformat,
        lambda item: datetime.strptime(item, "%m/%d/%Y"),
        lambda item: datetime.strptime(item, "%m/%d/%Y %I:%M:%S %p"),
        _parse_rfc_en_us,
    )
    for parser in parsers:
        try:
            return parser(value).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"{filename}: invalid en-US date in {column}")


def _validate_loaded_at(value: str, *, filename: str) -> str:
    iso_candidates = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f")
    for pattern in iso_candidates:
        try:
            datetime.strptime(value, pattern)
            return NON_NULL_TIMESTAMPTZ
        except ValueError:
            pass
    for pattern in ("%m/%d/%Y %I:%M:%S %p",):
        try:
            datetime.strptime(value, pattern)
            return NON_NULL_TIMESTAMPTZ
        except ValueError:
            continue
    try:
        _parse_rfc_en_us(value)
        return NON_NULL_TIMESTAMPTZ
    except ValueError:
        pass
    raise ValueError(f"{filename}: loaded_at is not a parseable en-US timestamp")


def _normalize_value(value: str, column: Column, *, filename: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError(f"{filename}: embedded line break in {column.name}")
    if value == "":
        if column.nullable:
            return NULL
        raise ValueError(f"{filename}: blank value in required column {column.name}")

    if column.kind == "text":
        return value
    if column.kind == "dataset_version_id":
        if not INTEGER_PATTERN.fullmatch(value) or int(value) <= 0:
            raise ValueError(f"{filename}: dataset_version_id must be a positive integer")
        return NON_NULL_BIGINT
    if column.kind == "loaded_at":
        return _validate_loaded_at(value, filename=filename)
    if column.kind == "date":
        return _parse_date(value, filename=filename, column=column.name)
    if column.kind == "integer":
        if not INTEGER_PATTERN.fullmatch(value):
            raise ValueError(f"{filename}: invalid ASCII integer in {column.name}")
        return str(int(value))
    if column.kind == "boolean":
        lowered = value.lower()
        if lowered not in {"true", "false"}:
            raise ValueError(f"{filename}: invalid boolean in {column.name}")
        return lowered
    if column.kind == "float":
        if not FLOAT_PATTERN.fullmatch(value):
            raise ValueError(f"{filename}: invalid ASCII float in {column.name}")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{filename}: non-finite float in {column.name}")
        return format(number, ".17g")
    raise AssertionError(f"unsupported column kind: {column.kind}")


def _read_export(path: Path, schema: ExportSchema) -> tuple[list[str], list[dict[str, str]], int]:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{path.name}: UTF-8 BOM is forbidden")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{path.name}: input is not UTF-8") from error
    if b"\r" in data.replace(b"\r\n", b""):
        raise ValueError(f"{path.name}: bare CR is forbidden")

    reader = csv.reader(text.splitlines(), delimiter="\t", quotechar='"', strict=True)
    try:
        raw_rows = list(reader)
    except csv.Error as error:
        raise ValueError(f"{path.name}: invalid TSV quoting") from error
    if not raw_rows:
        raise ValueError(f"{path.name}: empty export")

    header = [_normalized_header(value) for value in raw_rows[0]]
    expected_header = [column.name for column in schema.columns]
    if header != expected_header:
        raise ValueError(f"{path.name}: missing, additional, or reordered columns")
    if len(raw_rows) - 1 != schema.row_count:
        raise ValueError(
            f"{path.name}: expected {schema.row_count} rows, found {len(raw_rows) - 1}"
        )

    rows: list[dict[str, str]] = []
    source_ids: set[int] = set()
    for line_number, values in enumerate(raw_rows[1:], start=2):
        if len(values) != len(schema.columns):
            raise ValueError(f"{path.name}:{line_number}: wrong column count")
        normalized: dict[str, str] = {}
        for column, value in zip(schema.columns, values, strict=True):
            if column.kind == "dataset_version_id":
                if not INTEGER_PATTERN.fullmatch(value) or int(value) <= 0:
                    raise ValueError(
                        f"{path.name}:{line_number}: dataset_version_id must be positive"
                    )
                source_ids.add(int(value))
            normalized[column.name] = _normalize_value(
                value, column, filename=path.name
            )
        rows.append(normalized)
    if len(source_ids) != 1:
        raise ValueError(f"{path.name}: dataset_version_id is not unique and coherent")
    rows.sort(key=schema.sort_key)
    return expected_header, rows, next(iter(source_ids))


def _serialize(header: list[str], rows: Iterable[dict[str, str]]) -> bytes:
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.writer(
        buffer,
        delimiter="\t",
        quotechar='"',
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )
    writer.writerow(header)
    for row in rows:
        writer.writerow([row[column] for column in header])
    return buffer.getvalue().encode("utf-8")


def normalize_exports(raw_directory: Path, output_directory: Path) -> dict[str, dict[str, object]]:
    actual_files = {path.name for path in raw_directory.iterdir() if path.is_file()}
    expected_files = set(SCHEMAS)
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        additional = sorted(actual_files - expected_files)
        raise ValueError(f"raw export set mismatch: missing={missing}, additional={additional}")

    prepared: dict[str, bytes] = {}
    identifiers: set[int] = set()
    summary: dict[str, dict[str, object]] = {}
    for filename, schema in SCHEMAS.items():
        header, rows, source_id = _read_export(raw_directory / filename, schema)
        identifiers.add(source_id)
        payload = _serialize(header, rows)
        if payload.startswith(b"\xef\xbb\xbf") or b"\r" in payload:
            raise AssertionError(f"{filename}: output encoding invariant failed")
        if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
            raise AssertionError(f"{filename}: final LF invariant failed")
        prepared[filename] = payload
        summary[filename] = {
            "row_count": schema.row_count,
            "sha256": hashlib.sha256(payload).hexdigest().upper(),
        }
    if len(identifiers) != 1:
        raise ValueError("dataset_version_id differs across DAX exports")

    output_directory.mkdir(parents=True, exist_ok=True)
    for filename, payload in prepared.items():
        (output_directory / filename).write_bytes(payload)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "raw",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "query-results",
    )
    arguments = parser.parse_args()
    summary = normalize_exports(arguments.raw_dir, arguments.output_dir)
    for filename in sorted(summary):
        item = summary[filename]
        print(f"{filename}\trows={item['row_count']}\tsha256={item['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
