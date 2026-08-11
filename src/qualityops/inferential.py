"""Auditable inferential statistical analyses."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from scipy.stats import f as f_distribution
from scipy.stats import t as t_distribution


@dataclass(frozen=True, slots=True)
class OneWayAnovaResult:
    """Results from a classical one-way ANOVA."""

    group_count: int
    observation_count: int
    df_between: int
    df_within: int
    ss_between: float
    ss_within: float
    ss_total: float
    ms_between: float
    ms_within: float
    f_statistic: float
    p_value: float


def one_way_anova(
    groups: Mapping[str, Iterable[float]],
) -> OneWayAnovaResult:
    """Perform a classical one-way ANOVA assuming equal variances."""

    if len(groups) < 2:
        raise ValueError("One-way ANOVA requires at least two groups")

    validated_groups: dict[str, list[float]] = {}

    for label, values in groups.items():
        observations = [float(value) for value in values]

        if len(observations) < 2:
            raise ValueError(
                f"Group {label!r} must contain at least two observations"
            )

        if not all(math.isfinite(value) for value in observations):
            raise ValueError(
                f"Group {label!r} must contain only finite observations"
            )

        validated_groups[str(label)] = observations

    observation_count = sum(
        len(observations)
        for observations in validated_groups.values()
    )
    group_count = len(validated_groups)

    all_observations = [
        value
        for observations in validated_groups.values()
        for value in observations
    ]
    grand_mean = math.fsum(all_observations) / observation_count

    group_means = {
        label: math.fsum(observations) / len(observations)
        for label, observations in validated_groups.items()
    }

    ss_between = math.fsum(
        len(validated_groups[label])
        * (group_mean - grand_mean) ** 2
        for label, group_mean in group_means.items()
    )

    ss_within = math.fsum(
        math.fsum(
            (observation - group_means[label]) ** 2
            for observation in observations
        )
        for label, observations in validated_groups.items()
    )

    ss_total = math.fsum(
        (observation - grand_mean) ** 2
        for observation in all_observations
    )

    df_between = group_count - 1
    df_within = observation_count - group_count

    ms_between = ss_between / df_between
    ms_within = ss_within / df_within

    if ms_within <= 0:
        raise ValueError(
            "Within-group variation must be positive for one-way ANOVA"
        )

    f_statistic = ms_between / ms_within
    p_value = float(
        f_distribution.sf(
            f_statistic,
            df_between,
            df_within,
        )
    )

    return OneWayAnovaResult(
        group_count=group_count,
        observation_count=observation_count,
        df_between=df_between,
        df_within=df_within,
        ss_between=ss_between,
        ss_within=ss_within,
        ss_total=ss_total,
        ms_between=ms_between,
        ms_within=ms_within,
        f_statistic=f_statistic,
        p_value=p_value,
    )


@dataclass(frozen=True, slots=True)
class PearsonCorrelationResult:
    """Results from a Pearson product-moment correlation."""

    observation_count: int
    correlation: float
    p_value: float


def pearson_correlation(
    x: Iterable[float],
    y: Iterable[float],
) -> PearsonCorrelationResult:
    """Calculate Pearson correlation and its two-sided p-value."""

    x_values = [float(value) for value in x]
    y_values = [float(value) for value in y]

    if len(x_values) != len(y_values):
        raise ValueError("Pearson correlation requires equal-length variables")

    observation_count = len(x_values)

    if observation_count < 3:
        raise ValueError(
            "Pearson correlation requires at least three paired observations"
        )

    if not all(
        math.isfinite(value)
        for value in (*x_values, *y_values)
    ):
        raise ValueError(
            "Pearson correlation requires only finite observations"
        )

    x_mean = math.fsum(x_values) / observation_count
    y_mean = math.fsum(y_values) / observation_count

    x_sum_squares = math.fsum(
        (value - x_mean) ** 2
        for value in x_values
    )
    y_sum_squares = math.fsum(
        (value - y_mean) ** 2
        for value in y_values
    )

    if x_sum_squares <= 0 or y_sum_squares <= 0:
        raise ValueError(
            "Both variables must have positive variation"
        )

    cross_product = math.fsum(
        (x_value - x_mean) * (y_value - y_mean)
        for x_value, y_value in zip(x_values, y_values)
    )

    correlation = cross_product / math.sqrt(
        x_sum_squares * y_sum_squares
    )

    correlation = max(-1.0, min(1.0, correlation))
    degrees_of_freedom = observation_count - 2

    if abs(correlation) == 1.0:
        p_value = 0.0
    else:
        t_statistic = correlation * math.sqrt(
            degrees_of_freedom / (1.0 - correlation**2)
        )
        p_value = float(
            2.0
            * t_distribution.sf(
                abs(t_statistic),
                degrees_of_freedom,
            )
        )

    return PearsonCorrelationResult(
        observation_count=observation_count,
        correlation=correlation,
        p_value=p_value,
    )


@dataclass(frozen=True, slots=True)
class SimpleLinearRegressionResult:
    """Results from an ordinary least-squares simple linear regression."""

    observation_count: int
    slope: float
    intercept: float
    r_squared: float
    p_value: float
    slope_standard_error: float


def simple_linear_regression(
    x: Iterable[float],
    y: Iterable[float],
) -> SimpleLinearRegressionResult:
    """Fit a simple linear regression and test the slope."""

    x_values = [float(value) for value in x]
    y_values = [float(value) for value in y]

    if len(x_values) != len(y_values):
        raise ValueError(
            "Simple linear regression requires equal-length variables"
        )

    observation_count = len(x_values)

    if observation_count < 3:
        raise ValueError(
            "Simple linear regression requires at least three paired observations"
        )

    if not all(
        math.isfinite(value)
        for value in (*x_values, *y_values)
    ):
        raise ValueError(
            "Simple linear regression requires only finite observations"
        )

    x_mean = math.fsum(x_values) / observation_count
    y_mean = math.fsum(y_values) / observation_count

    x_sum_squares = math.fsum(
        (value - x_mean) ** 2
        for value in x_values
    )
    y_sum_squares = math.fsum(
        (value - y_mean) ** 2
        for value in y_values
    )

    if x_sum_squares <= 0:
        raise ValueError(
            "Predictor must have positive variation"
        )

    if y_sum_squares <= 0:
        raise ValueError(
            "Response must have positive variation"
        )

    cross_product = math.fsum(
        (x_value - x_mean) * (y_value - y_mean)
        for x_value, y_value in zip(x_values, y_values)
    )

    slope = cross_product / x_sum_squares
    intercept = y_mean - slope * x_mean

    residual_sum_squares = math.fsum(
        (
            y_value
            - (intercept + slope * x_value)
        ) ** 2
        for x_value, y_value in zip(x_values, y_values)
    )

    r_squared = 1.0 - (
        residual_sum_squares / y_sum_squares
    )
    r_squared = max(0.0, min(1.0, r_squared))

    degrees_of_freedom = observation_count - 2
    residual_mean_square = (
        residual_sum_squares / degrees_of_freedom
    )
    slope_standard_error = math.sqrt(
        residual_mean_square / x_sum_squares
    )

    if slope_standard_error == 0:
        p_value = 0.0
    else:
        t_statistic = slope / slope_standard_error
        p_value = float(
            2.0
            * t_distribution.sf(
                abs(t_statistic),
                degrees_of_freedom,
            )
        )

    return SimpleLinearRegressionResult(
        observation_count=observation_count,
        slope=slope,
        intercept=intercept,
        r_squared=r_squared,
        p_value=p_value,
        slope_standard_error=slope_standard_error,
    )