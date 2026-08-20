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
    PearsonCorrelationResult,
    SimpleLinearRegressionResult,
    one_way_anova,
    pearson_correlation,
    simple_linear_regression,
)
from qualityops.secom import SecomAuditResult, audit_secom, load_secom
from qualityops.persistence import (
    SecomPersistenceResult,
    persist_secom,
)
from qualityops.spc import (
    SubgroupCapabilityResult,
    XbarRChartResult,
    analyze_subgroup_capability,
    analyze_xbar_r,
    calculate_cpm,
    load_wide_subgroups,
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
    "PearsonCorrelationResult",
    "SimpleLinearRegressionResult",
    "one_way_anova",
    "pearson_correlation",
    "simple_linear_regression",
    "SecomAuditResult",
    "audit_secom",
    "load_secom",
    "SecomPersistenceResult",
    "persist_secom",
    "SubgroupCapabilityResult",
    "XbarRChartResult",
    "analyze_subgroup_capability",
    "analyze_xbar_r",
    "calculate_cpm",
    "load_wide_subgroups",
]

__version__ = "0.2.0"
