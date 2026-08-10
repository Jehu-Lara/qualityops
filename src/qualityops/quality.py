"""Serializable data-quality checks for tabular inputs."""

from __future__ import annotations

from typing import Any

import pandas as pd


def summarize_dataframe(dataframe: pd.DataFrame) -> dict[str, Any]:
    """Return shape, schema, missingness, empty-row, and duplication metrics."""

    missing_by_column = {
        str(column): int(count)
        for column, count in dataframe.isna().sum().items()
    }
    return {
        "row_count": int(len(dataframe)),
        "column_count": int(len(dataframe.columns)),
        "columns": [str(column) for column in dataframe.columns],
        "missing_cell_count": int(dataframe.isna().sum().sum()),
        "missing_values": missing_by_column,
        "empty_rows": int(dataframe.isna().all(axis=1).sum()),
        "duplicate_rows": int(dataframe.duplicated().sum()),
        "data_types": {
            str(column): str(dtype)
            for column, dtype in dataframe.dtypes.items()
        },
    }
