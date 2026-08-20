# Changelog

All notable changes are documented here. The project follows semantic versioning while it remains in alpha development.

## Unreleased

### Added

- Added equal-size Xbar-R analysis with `Rbar/d2` within-sigma estimation,
  three-sigma limits, Test 1, subgroup-derived capability indices and a public
  CLI path.
- Added a hash-locked synthetic n=4 validation dataset and unrounded Minitab
  22.5.1 reconciliation for Xbar-R, `Cp/Cpk/Pp/Ppk/Cpm`, plus documented
  normality evidence and claim boundaries.
- Added an explicitly assumption-driven ROI planning model with no claimed
  realized savings.

- Added a normalized PostgreSQL 16 persistence layer for verified SECOM data,
  including named relational constraints, Alembic migration and rollback,
  an idempotent transactional loader, and twenty audited read-only SQL queries.
- Added the public UCI SECOM manufacturing dataset with verified acquisition hashes, deterministic quality auditing, documented provenance, and CLI support.
- Added the one-page Power BI PBIP/PBIR/TMDL Process Health project,
  PostgreSQL least-privilege reader lifecycle, six reconciled DAX validation
  exports, accessibility metadata, and an authentic sanitized canvas preview.
  PR checks and Required-check governance remain pending.

## 0.2.0 — 2026-08-09

### Changed

- Corrected statistical terminology: overall sample variation now reports `Pp/Ppk`.
- Restricted `Cp/Cpk` to analyses with an explicitly supplied within-subgroup sigma.
- Reorganized the code into an installable `src/qualityops` package with a public CLI.
- Reframed the DMAIC source as an illustrative case prepared for evaluation, without claiming certification, implementation, or realized savings.

### Added

- Strict measurement-column extraction and source metadata.
- JSON command output, expanded unit tests, CI, dependency monitoring, and portfolio claim boundaries.

## 0.1.0 — 2026-08-09

- Initial Excel loading, quality summary, sample statistics, and capability formulas.
