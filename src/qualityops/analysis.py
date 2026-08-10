"""Process-performance and capability calculations with explicit estimators.

Overall sample variation is used for Pp/Ppk. Cp/Cpk are calculated only when
the caller supplies a within-subgroup sigma estimated by an appropriate,
documented method.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass


def _validated_values(values: Iterable[float]) -> list[float]:
    observations = [float(value) for value in values]
    if not observations:
        raise ValueError("At least one numeric observation is required")
    if not all(math.isfinite(value) for value in observations):
        raise ValueError("Observations must contain only finite numbers")
    return observations


def _validate_specifications(lsl: float, usl: float) -> tuple[float, float]:
    lower = float(lsl)
    upper = float(usl)
    if not math.isfinite(lower) or not math.isfinite(upper):
        raise ValueError("Specification limits must be finite")
    if lower >= upper:
        raise ValueError("LSL must be lower than USL")
    return lower, upper


def _validate_sigma(sigma: float, label: str) -> float:
    validated = float(sigma)
    if not math.isfinite(validated) or validated <= 0:
        raise ValueError(f"{label} must be a finite positive number")
    return validated


def _spread_index(sigma: float, lsl: float, usl: float) -> float:
    lower, upper = _validate_specifications(lsl, usl)
    return (upper - lower) / (6 * sigma)


def _lower_index(mean: float, sigma: float, lsl: float) -> float:
    return (mean - lsl) / (3 * sigma)


def _upper_index(mean: float, sigma: float, usl: float) -> float:
    return (usl - mean) / (3 * sigma)


def _validate_mean(mean: float) -> float:
    validated = float(mean)
    if not math.isfinite(validated):
        raise ValueError("Mean must be finite")
    return validated


def calculate_mean(values: Iterable[float]) -> float:
    """Return the arithmetic mean of finite observations."""

    observations = _validated_values(values)
    return math.fsum(observations) / len(observations)


def calculate_sample_std(values: Iterable[float]) -> float:
    """Return overall sample standard deviation using Bessel's correction."""

    observations = _validated_values(values)
    if len(observations) < 2:
        raise ValueError("Sample standard deviation requires at least two observations")

    mean = calculate_mean(observations)
    squared_deviations = math.fsum(
        (observation - mean) ** 2 for observation in observations
    )
    return math.sqrt(squared_deviations / (len(observations) - 1))


def calculate_pp(overall_sigma: float, lsl: float, usl: float) -> float:
    """Return Pp using overall process variation."""

    sigma = _validate_sigma(overall_sigma, "Overall standard deviation")
    return _spread_index(sigma, lsl, usl)


def calculate_ppk(
    mean: float, overall_sigma: float, lsl: float, usl: float
) -> float:
    """Return Ppk using overall process variation."""

    lower, upper = _validate_specifications(lsl, usl)
    center = _validate_mean(mean)
    sigma = _validate_sigma(overall_sigma, "Overall standard deviation")
    return min(
        _lower_index(center, sigma, lower),
        _upper_index(center, sigma, upper),
    )


def calculate_cp(within_sigma: float, lsl: float, usl: float) -> float:
    """Return Cp using a caller-supplied within-subgroup sigma."""

    sigma = _validate_sigma(within_sigma, "Within-subgroup standard deviation")
    return _spread_index(sigma, lsl, usl)


def calculate_cpk(
    mean: float, within_sigma: float, lsl: float, usl: float
) -> float:
    """Return Cpk using a caller-supplied within-subgroup sigma."""

    lower, upper = _validate_specifications(lsl, usl)
    center = _validate_mean(mean)
    sigma = _validate_sigma(within_sigma, "Within-subgroup standard deviation")
    return min(
        _lower_index(center, sigma, lower),
        _upper_index(center, sigma, upper),
    )


@dataclass(frozen=True, slots=True)
class OverallPerformanceResult:
    """Overall process-performance metrics based on sample variation."""

    count: int
    mean: float
    overall_sample_std: float
    pp: float
    ppl: float
    ppu: float
    ppk: float
    lsl: float
    usl: float


@dataclass(frozen=True, slots=True)
class PotentialCapabilityResult:
    """Potential capability metrics based on supplied within variation."""

    count: int
    mean: float
    within_sigma: float
    cp: float
    cpl: float
    cpu: float
    cpk: float
    lsl: float
    usl: float


@dataclass(frozen=True, slots=True)
class ProcessAnalysis:
    """Combined overall and optional within-capability results."""

    overall: OverallPerformanceResult
    potential: PotentialCapabilityResult | None


def analyze_overall_performance(
    values: Iterable[float], lsl: float, usl: float
) -> OverallPerformanceResult:
    """Calculate mean, overall sample variation, Pp, PPL, PPU, and Ppk."""

    observations = _validated_values(values)
    if len(observations) < 2:
        raise ValueError("Process analysis requires at least two observations")

    lower, upper = _validate_specifications(lsl, usl)
    mean = calculate_mean(observations)
    sigma = calculate_sample_std(observations)
    sigma = _validate_sigma(sigma, "Overall standard deviation")
    ppl = _lower_index(mean, sigma, lower)
    ppu = _upper_index(mean, sigma, upper)
    return OverallPerformanceResult(
        count=len(observations),
        mean=mean,
        overall_sample_std=sigma,
        pp=calculate_pp(sigma, lower, upper),
        ppl=ppl,
        ppu=ppu,
        ppk=min(ppl, ppu),
        lsl=lower,
        usl=upper,
    )


def analyze_capability(
    values: Iterable[float], lsl: float, usl: float, within_sigma: float
) -> PotentialCapabilityResult:
    """Calculate Cp/Cpk from an explicitly supplied within-subgroup sigma."""

    observations = _validated_values(values)
    lower, upper = _validate_specifications(lsl, usl)
    mean = calculate_mean(observations)
    sigma = _validate_sigma(within_sigma, "Within-subgroup standard deviation")
    cpl = _lower_index(mean, sigma, lower)
    cpu = _upper_index(mean, sigma, upper)
    return PotentialCapabilityResult(
        count=len(observations),
        mean=mean,
        within_sigma=sigma,
        cp=calculate_cp(sigma, lower, upper),
        cpl=cpl,
        cpu=cpu,
        cpk=min(cpl, cpu),
        lsl=lower,
        usl=upper,
    )


def analyze_process(
    values: Iterable[float],
    lsl: float,
    usl: float,
    within_sigma: float | None = None,
) -> ProcessAnalysis:
    """Return overall metrics and optional potential capability metrics."""

    observations = _validated_values(values)
    overall = analyze_overall_performance(observations, lsl=lsl, usl=usl)
    potential = None
    if within_sigma is not None:
        potential = analyze_capability(
            observations,
            lsl=lsl,
            usl=usl,
            within_sigma=within_sigma,
        )
    return ProcessAnalysis(overall=overall, potential=potential)
