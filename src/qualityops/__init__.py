"""Auditable process-performance and capability calculations."""

from qualityops.analysis import (
    OverallPerformanceResult,
    PotentialCapabilityResult,
    ProcessAnalysis,
    analyze_capability,
    analyze_overall_performance,
    analyze_process,
    calculate_cp,
    calculate_cpk,
    calculate_mean,
    calculate_pp,
    calculate_ppk,
    calculate_sample_std,
)

from qualityops.inferential import (
    OneWayAnovaResult,
    one_way_anova,
)

__all__ = [
    "OverallPerformanceResult",
    "PotentialCapabilityResult",
    "ProcessAnalysis",
    "analyze_capability",
    "analyze_overall_performance",
    "analyze_process",
    "calculate_cp",
    "calculate_cpk",
    "calculate_mean",
    "calculate_pp",
    "calculate_ppk",
    "calculate_sample_std",
    "OneWayAnovaResult",
    "one_way_anova",
]

__version__ = "0.2.0"
