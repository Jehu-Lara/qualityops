"""Xbar-R control charts and subgroup capability with explicit assumptions."""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from qualityops.analysis import (
    OverallPerformanceResult,
    PotentialCapabilityResult,
    analyze_capability,
    analyze_overall_performance,
)


# Minitab's published unbiasing constants for subgroup sizes 2 through 10.
# The validation claim in this repository is limited to the n=4 reference case.
_RANGE_CONSTANTS: dict[int, tuple[float, float]] = {
    2: (1.128, 0.8525),
    3: (1.693, 0.8884),
    4: (2.059, 0.8798),
    5: (2.326, 0.8641),
    6: (2.534, 0.8480),
    7: (2.704, 0.8332),
    8: (2.847, 0.8198),
    9: (2.970, 0.8078),
    10: (3.078, 0.7971),
}


@dataclass(frozen=True)
class XbarRChartResult:
    """Calculated points, limits, and Test 1 results for an Xbar-R chart."""

    subgroup_count: int
    subgroup_size: int
    grand_mean: float
    average_range: float
    within_sigma: float
    xbar_lcl: float
    xbar_ucl: float
    range_lcl: float
    range_ucl: float
    subgroup_means: tuple[float, ...]
    subgroup_ranges: tuple[float, ...]
    xbar_test1_violations: tuple[int, ...]
    range_test1_violations: tuple[int, ...]


@dataclass(frozen=True)
class SubgroupCapabilityResult:
    """Xbar-R evidence plus overall and within capability results."""

    chart: XbarRChartResult
    overall: OverallPerformanceResult
    potential: PotentialCapabilityResult
    target: float | None
    cpm: float | None


def _validated_subgroups(
    subgroups: Iterable[Iterable[float]],
) -> tuple[tuple[float, ...], ...]:
    rows: list[tuple[float, ...]] = []
    for subgroup_index, subgroup in enumerate(subgroups, start=1):
        values = tuple(float(value) for value in subgroup)
        if not values:
            raise ValueError(f"Subgroup {subgroup_index} is empty")
        if not all(math.isfinite(value) for value in values):
            raise ValueError(
                f"Subgroup {subgroup_index} contains a non-finite value"
            )
        rows.append(values)

    if len(rows) < 2:
        raise ValueError("At least two subgroups are required")

    subgroup_size = len(rows[0])
    if subgroup_size not in _RANGE_CONSTANTS:
        raise ValueError("Subgroup size must be between 2 and 10")
    if any(len(row) != subgroup_size for row in rows):
        raise ValueError("All subgroups must have the same size")
    return tuple(rows)


def analyze_xbar_r(
    subgroups: Iterable[Iterable[float]],
) -> XbarRChartResult:
    """Calculate a three-sigma Xbar-R chart using the Rbar/d2 estimator."""

    rows = _validated_subgroups(subgroups)
    subgroup_size = len(rows[0])
    d2, d3 = _RANGE_CONSTANTS[subgroup_size]
    subgroup_means = tuple(math.fsum(row) / subgroup_size for row in rows)
    subgroup_ranges = tuple(max(row) - min(row) for row in rows)
    observation_count = len(rows) * subgroup_size
    grand_mean = math.fsum(math.fsum(row) for row in rows) / observation_count
    average_range = math.fsum(subgroup_ranges) / len(subgroup_ranges)
    if average_range <= 0:
        raise ValueError("Average subgroup range must be positive")

    within_sigma = average_range / d2
    xbar_half_width = 3 * within_sigma / math.sqrt(subgroup_size)
    xbar_lcl = grand_mean - xbar_half_width
    xbar_ucl = grand_mean + xbar_half_width
    range_lcl = max(0.0, (d2 - 3 * d3) * within_sigma)
    range_ucl = (d2 + 3 * d3) * within_sigma

    xbar_violations = tuple(
        index
        for index, value in enumerate(subgroup_means, start=1)
        if value < xbar_lcl or value > xbar_ucl
    )
    range_violations = tuple(
        index
        for index, value in enumerate(subgroup_ranges, start=1)
        if value < range_lcl or value > range_ucl
    )
    return XbarRChartResult(
        subgroup_count=len(rows),
        subgroup_size=subgroup_size,
        grand_mean=grand_mean,
        average_range=average_range,
        within_sigma=within_sigma,
        xbar_lcl=xbar_lcl,
        xbar_ucl=xbar_ucl,
        range_lcl=range_lcl,
        range_ucl=range_ucl,
        subgroup_means=subgroup_means,
        subgroup_ranges=subgroup_ranges,
        xbar_test1_violations=xbar_violations,
        range_test1_violations=range_violations,
    )


def calculate_cpm(
    values: Iterable[float], lsl: float, usl: float, target: float
) -> float:
    """Calculate Cpm using root mean square deviation from the target."""

    observations = tuple(float(value) for value in values)
    if not observations:
        raise ValueError("At least one observation is required")
    if not all(math.isfinite(value) for value in observations):
        raise ValueError("Observations must be finite")
    lower, upper, center = float(lsl), float(usl), float(target)
    if not all(math.isfinite(value) for value in (lower, upper, center)):
        raise ValueError("Specification limits and target must be finite")
    if lower >= upper:
        raise ValueError("LSL must be less than USL")
    target_deviation = math.sqrt(
        math.fsum((value - center) ** 2 for value in observations)
        / len(observations)
    )
    if target_deviation <= 0:
        raise ValueError("Target deviation must be positive")
    return (upper - lower) / (6 * target_deviation)


def analyze_subgroup_capability(
    subgroups: Iterable[Iterable[float]],
    lsl: float,
    usl: float,
    target: float | None = None,
) -> SubgroupCapabilityResult:
    """Derive within sigma from subgroups and calculate capability indices."""

    rows = _validated_subgroups(subgroups)
    chart = analyze_xbar_r(rows)
    observations = tuple(value for row in rows for value in row)
    overall = analyze_overall_performance(observations, lsl=lsl, usl=usl)
    potential = analyze_capability(
        observations,
        lsl=lsl,
        usl=usl,
        within_sigma=chart.within_sigma,
    )
    cpm = None
    if target is not None:
        cpm = calculate_cpm(observations, lsl=lsl, usl=usl, target=target)
    return SubgroupCapabilityResult(
        chart=chart,
        overall=overall,
        potential=potential,
        target=None if target is None else float(target),
        cpm=cpm,
    )


def load_wide_subgroups(
    path: str | Path, measurement_columns: Sequence[str]
) -> tuple[tuple[float, ...], ...]:
    """Load equal-size rational subgroups from selected columns in a CSV file."""

    source = Path(path)
    columns = tuple(measurement_columns)
    if len(columns) < 2:
        raise ValueError("At least two measurement columns are required")
    if len(set(columns)) != len(columns):
        raise ValueError("Measurement column names must be unique")
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError("CSV file must include a header row")
        missing = [column for column in columns if column not in reader.fieldnames]
        if missing:
            raise ValueError(f"Missing measurement columns: {', '.join(missing)}")
        rows: list[tuple[float, ...]] = []
        for row_number, row in enumerate(reader, start=2):
            try:
                rows.append(tuple(float(row[column]) for column in columns))
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid measurement value on CSV row {row_number}"
                ) from error
    return _validated_subgroups(rows)
