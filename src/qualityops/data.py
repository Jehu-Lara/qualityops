"""Excel ingestion and explicit measurement extraction."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True, slots=True)
class MeasurementData:
    """Validated measurements plus ingestion metadata."""

    values: tuple[float, ...]
    source_row_count: int
    missing_count: int


def load_excel(path: str | Path, sheet_name: str | int = 0) -> pd.DataFrame:
    """Load one worksheet from an ``.xlsx`` workbook."""

    workbook_path = Path(path)
    if not workbook_path.is_file():
        raise FileNotFoundError(f"Excel file not found: {workbook_path}")
    if workbook_path.suffix.lower() != ".xlsx":
        raise ValueError("Expected an Excel workbook with extension .xlsx")

    loaded = pd.read_excel(workbook_path, sheet_name=sheet_name, engine="openpyxl")
    if not isinstance(loaded, pd.DataFrame):
        raise TypeError("Expected a single worksheet, not a workbook mapping")
    return loaded


def extract_measurements(
    dataframe: pd.DataFrame, column: str
) -> MeasurementData:
    """Extract finite numeric values and report dropped blank cells.

    Missing cells are excluded and counted. Non-numeric or infinite non-missing
    values are rejected instead of being silently coerced.
    """

    if column not in dataframe.columns:
        available = ", ".join(str(name) for name in dataframe.columns)
        raise KeyError(f"Column {column!r} not found. Available columns: {available}")

    series = dataframe[column]
    missing_count = int(series.isna().sum())
    non_missing = series[series.notna()]
    numeric = pd.to_numeric(non_missing, errors="coerce")
    invalid_mask = numeric.isna()
    if invalid_mask.any():
        rows = [str(index) for index in numeric.index[invalid_mask][:5]]
        raise ValueError(
            f"Column {column!r} contains non-numeric values at row indexes: "
            + ", ".join(rows)
        )

    values = tuple(float(value) for value in numeric.tolist())
    if not values:
        raise ValueError(f"Column {column!r} contains no numeric measurements")
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"Column {column!r} contains non-finite measurements")

    return MeasurementData(
        values=values,
        source_row_count=int(len(dataframe)),
        missing_count=missing_count,
    )


def load_measurements(
    path: str | Path, column: str, sheet_name: str | int = 0
) -> MeasurementData:
    """Load and validate one measurement column from an Excel worksheet."""

    return extract_measurements(load_excel(path, sheet_name=sheet_name), column)
