"""Auditable inferential statistical analyses."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from scipy.stats import f as f_distribution


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