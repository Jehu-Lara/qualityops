# Power BI Process Health

Status: **Complete — PR #19 merged via Rebase and merge; main e85c0c57907a44ea6c7d63b5ed333da4a432ef51; four main checks completed with SUCCESS; no release, tag, Power BI Service/Fabric publication, or gateway configuration. CHANGELOG.md remains under Unreleased.**

`QualityOpsProcessHealth.pbip` is a Power BI Desktop project over the canonical
SECOM version persisted in PostgreSQL 16. The report uses PBIR, the semantic
model uses TMDL, and connectivity is Import. Power BI is an independent
consumer of the existing persistence contract; it does not own the schema,
loader, migration, or audited SQL.

The project was created and reopened with Power BI Desktop 2.156.951.0 64-bit
(July 2026, Microsoft Store). That build treats `Measures` as a reserved table
name, so the five-table model uses `Process Health Measures` for the dedicated
measure table. No measure name or formula changed because of that compatibility
adjustment.

## Requirements

- Windows x86-64 and Power BI Desktop 2.156.951.0 64-bit for the frozen
  validation session;
- PostgreSQL 16 and `psql` 16;
- migrated disposable database `qualityops_test_secom` owned by
  `qualityops_test_owner`;
- canonical SECOM data loaded and reconciled;
- temporary login role `qualityops_powerbi_reader`, provisioned with the five
  scripts under `postgresql/`.

No external Npgsql installation was required. Power BI Service, Fabric,
gateway configuration, scheduled refresh, and publication are outside scope.

## Project formats and local state

- `QualityOpsProcessHealth.pbip` references one PBIR report.
- `QualityOpsProcessHealth.Report/definition/` is the PBIR report definition.
- `QualityOpsProcessHealth.SemanticModel/definition/` is the TMDL semantic
  model.
- `QualityOpsProcessHealth.SemanticModel/DAXQueries/` contains exactly six
  saved validation queries.

Power BI Desktop must be closed before an external PBIR or TMDL edit. Reopen
and save the project afterward so Desktop remains the syntax authority. The
following local artifacts are ignored and must never be staged: `.platform`,
`localSettings.json`, `cache.abf`, `unappliedChanges.json`, DAX/TMDL editor
state, raw validation exports, `.pbix`, `.pbit`, and `.pbids` files.

## Parameters and credentials

| Parameter | Initial value |
|---|---|
| `PostgreSQLServer` | `127.0.0.1:5432` |
| `PostgreSQLDatabase` | `qualityops_test_secom` |
| `DatasetCode` | `uci-secom` |
| `VersionLabel` | `uci-secom-acquisition-2026-08-10` |
| `ContentFingerprint` | `57856B2CA3ED8E782F88E6A9DEDC61623A4B370ED8442BB89B03BC3B44610BF7` |

The public parameters contain no credentials. Enter Database credentials for
`qualityops_powerbi_reader` through Power BI Desktop's local data-source
settings. Never place a username, password, DSN, or environment variable value
inside M, TMDL, PBIR, documentation, logs, or validation evidence.

## Refresh and model

1. Confirm PostgreSQL 16, Alembic revision `0001_secom_persistence`, and a
   second loader result of `already_loaded`.
2. Create the temporary reader as administrator, then harden and grant access
   as the database owner.
3. Open the PBIP, keep concurrent evaluations at the build minimum of two,
   disable background previews, and supply the reader credentials locally.
4. Refresh all four imported tables.
5. Confirm one `DatasetVersion`, 1,567 `Observation` rows, 590 `Sensor` rows,
   and 924,530 `Measurement` rows.

Power Query resolves the canonical version by dataset code, version label, and
fingerprint. A materialized guard requires exactly one positive version ID.
`Observation`, `Sensor`, and `Measurement` inner-join to that filtered version
inside PostgreSQL. Query folding was verified at each table's final `Selected`
step; no native SQL is embedded.

The model has exactly five tables and two single-direction relationships:

- `Observation[source_row]` 1 → * `Measurement[source_row]`;
- `Sensor[sensor_index]` 1 → * `Measurement[sensor_index]`.

`DatasetVersion` and `Process Health Measures` are disconnected. Auto
date/time and relationship autodetection are disabled.

## DAX validation

Execute the six saved DAX queries in DAX Query View and copy each complete
Results grid into the ignored `validation/raw/` directory. Power BI Desktop
2.156.951.0 returns BLANK for zero-valued grouped measures, so only queries 05
and 07 apply explicit `COALESCE(..., 0)` to the affected output columns.

Run:

```powershell
.\.venv\Scripts\python.exe powerbi\validation\normalize_exports.py
```

The standard-library normalizer accepts only the documented en-US raw formats,
including the exact RFC form emitted by the frozen build. It replaces the
version ID and load timestamp with non-sensitive sentinels, writes UTF-8 TSV
with LF, rejects non-finite numbers, and reports SHA-256 hashes. The six
normalized results contain 1, 1, 2, 86, 590, and 590 rows and have been
reconciled with zero mismatches against the audited SQL and direct Python
oracles.

## Reader lifecycle

The scripts in `postgresql/` separate administrator and owner authority. The
reader has `LOGIN`, `NOINHERIT`, connection limit five, no memberships, and
only `CONNECT`, schema `USAGE`, and `SELECT` on the five contractual
relations. Provisioning consumes a temporary hexadecimal password from the
process environment. Cleanup revokes access as owner and drops the role as
administrator without `CASCADE`.

## Local visual evidence and known preview limitations

The `Process Health` page contains exactly 12 objects: title, reconciliation
status, five KPI cards, four native charts, and the attribution footer. The ten
informative visuals have non-empty alt text and deterministic tab order; all 90
pairwise visual interactions are `None`. The authentic canvas-only preview is
[`docs/assets/powerbi-process-health.png`](../docs/assets/powerbi-process-health.png),
and `validation/validation-summary.json` records the frozen validation session.

`powerbi-report-author` 0.1.4 reports `PBIR_SCHEMA_UNREACHABLE` for the
build-generated `visualContainer/2.11.0` schema URL. This is a validator schema
fetch warning, not a Desktop load error: Power BI Desktop 2.156.951.0 reopened,
reloaded, and rendered the same PBIR successfully. At the contractual 230 px
ranking height, the native clustered bar charts retain an internal scrollbar.
The screenshot therefore shows the initial ranked viewport; DAX output, Top 10
filters, deterministic rank order, and all ten members are validated separately.

PBIP, PBIR, and TMDL remain preview features in the frozen Desktop build. This
project is a local portfolio demonstration, not a production deployment.

## Licensing

M, DAX, TMDL, PBIR, Python, SQL provisioning scripts, theme, and project-written
documentation are MIT-licensed. Normalized TSV results, the validation summary,
and the Power BI screenshot are derived from SECOM and remain CC BY 4.0.
