# QualityOps 

Auditable process-performance and capability analysis for manufacturing data.

QualityOps is a focused Python portfolio project for loading measurement data, exposing basic data-quality risks, and reproducing selected Minitab metrics with explicit statistical assumptions. The implementation favors traceability and correct terminology over a large feature list.

> **Portfolio disclosure:** this repository is inspired by an illustrative DMAIC/PCBA case study prepared for Green Belt Level II evaluation. It does not claim CSSC approval, physical implementation in a factory, validated production savings, or use of confidential company data.

## Why this repository exists

Process-capability reports can look precise while hiding important choices about subgrouping, missing data, process stability, and the standard-deviation estimator. This project makes those choices visible in code and documentation.

The current release provides:

- `.xlsx` ingestion with explicit worksheet selection;
- schema, missing-cell, empty-row, and duplicate-row checks;
- strict numeric-column extraction that rejects invalid or infinite values;
- mean and overall sample standard deviation;
- `Pp`, `PPL`, `PPU`, and `Ppk` from overall sample variation;
- optional `Cp`, `CPL`, `CPU`, and `Cpk` only when a documented within-subgroup sigma is supplied;
- JSON output suitable for later dashboards or APIs;
- automated tests and a GitHub Actions matrix for Python 3.11–3.13.

## Statistical contract

This distinction is intentional:

| Metric family | Variation used | Interpretation in this project |
|---|---|---|
| `Pp` / `Ppk` | Overall sample standard deviation (`n - 1`) | Observed overall process performance |
| `Cp` / `Cpk` | Caller-supplied within-subgroup standard deviation | Potential within-subgroup capability |

The software does **not** infer a within-subgroup estimator from ungrouped observations. It also does not establish process stability, normality, measurement-system adequacy, or causal improvement. Those must be assessed before capability figures support an operational decision.

Minitab uses overall standard deviation for `Pp/Ppk` and within-subgroup standard deviation for `Cp/Cpk`; see the [official Minitab process-data guidance](https://support.minitab.com/en-us/minitab/help-and-how-to/quality-and-process-improvement/capability-analysis/how-to/capability-analysis/normal-capability-analysis/interpret-the-results/all-statistics-and-graphs/process-data/).

## Quick start

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e .
python -m unittest discover -v
```

Inspect one workbook:

```bash
qualityops inspect data/measurements.xlsx --sheet 0
```

Analyze an Excel column using overall variation:

```bash
qualityops analyze \
  --file data/measurements.xlsx \
  --column measurement \
  --lsl 14 \
  --usl 16
```

Analyze inline values and include `Cp/Cpk` only when the within-subgroup sigma has been independently established:

```bash
qualityops analyze \
  --values 9 10 11 \
  --lsl 7 \
  --usl 13 \
  --within-sigma 0.5
```

The command returns structured JSON. Blank measurement cells are excluded and counted; invalid non-blank values stop the analysis.

## Repository structure

```text
qualityops/
├── .github/               # continuous integration and dependency updates
├── data/                  # local-only measurement files
├── docs/                  # validation protocol and claim boundaries
├── notebooks/             # exploration only
├── powerbi/               # future Process Health page
├── src/qualityops/        # installable Python package and CLI
├── tests/                 # deterministic automated tests
├── CHANGELOG.md
├── ROADMAP.md
└── pyproject.toml
```

## Validation

The repository separates two validation tracks:

1. Compare mean, overall standard deviation, `Pp`, and `Ppk` against Minitab using the same observations, filters, limits, and precision.
2. Compare `Cp` and `Cpk` only after recording Minitab's within-subgroup estimator and supplying the matching sigma to Python.

Use [docs/minitab-validation.md](docs/minitab-validation.md) and record results from the included template. Automated unit tests verify the implementation against analytically known examples; they do not replace validation on the intended dataset.

## Scope and responsible use

- Raw datasets and Power BI binaries are ignored to reduce accidental disclosure.
- The package is an educational portfolio artifact in alpha status, not a validated production quality-management system.
- Capability indices should not be interpreted without process knowledge, control-chart evidence, distribution assessment, and a trustworthy measurement system.
- AI-generated recommendations, databases, APIs, and production deployment are intentionally outside the current release.

See [docs/portfolio-claims.md](docs/portfolio-claims.md) for statements that are and are not supported by the current evidence.
