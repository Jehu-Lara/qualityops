# SECOM Process Health decision view

## Status and decision objective

Status: **Gate A and Gate B complete — merge pending explicit authorization.**

The intended deliverable is one Power BI page named `Process Health` that
communicates verified dataset health, observed pass/fail outcomes, daily fail
rate, sensor missingness, and standardized pass/fail mean differences. It is a
descriptive portfolio demonstration. Associations do not establish causality,
root cause, operational importance, or process capability.

The PBIP opened, imported the canonical SECOM data, reconciled six DAX result
sets against audited SQL and independent Python oracles, and reopened after the
final external edits. The completed page and its authentic canvas capture are
durable Gate A evidence. Gate B is complete: Draft PR #19 was created and all
four Required checks passed. Merge remains pending explicit authorization. No
release, tag, or Power BI Service publication has occurred.

## Architecture

```text
PostgreSQL 16
  -> PostgreSQL.Database navigation and foldable canonical-version joins
  -> four imported tables plus one calculated measure table
  -> two single-direction relationships and explicit DAX measures
  -> one PBIR report page
  -> DAX Query View exports
  -> normalized TSV evidence and independent reconciliation
```

Power BI remains a consuming layer. The existing PostgreSQL schema, Alembic
migration, Psycopg loader transaction, advisory lock, public Python API, CLI,
and twenty analytical SQL queries are unchanged.

## Why Import

Import gives predictable local demonstration performance, keeps observation of
the future static preview independent of a live database, and avoids adding a
gateway or Power BI Service. The imported cache remains local in `.pbi/cache.abf`
and is ignored. This choice does not imply real-time refresh, deployment, or
industrial scale.

## Canonical selection and folding

Five public text parameters identify the source and canonical version. M uses
`PostgreSQL.Database` object navigation, not `Value.NativeQuery`, concatenated
SQL, or a credential-bearing DSN. `CanonicalVersionRows` joins `dataset` and
`dataset_version` by `dataset_id`, filters by code, label, and uppercase content
fingerprint, and retains the internal version ID only for source filtering.

`CanonicalVersionGuard` buffers the small identity result and raises a visible
error unless it contains exactly one row with a positive ID. The three large
queries join their source relation to the canonical version before selecting
report columns. Power BI Desktop 2.156.951.0 verified native query folding at
the final `Selected` step for `Observation`, `Sensor`, and `Measurement`.

## Semantic model

The five visible tables are `DatasetVersion`, `Observation`, `Sensor`,
`Measurement`, and `Process Health Measures`. The last name is a documented
compatibility amendment: Desktop 2.156.951.0 rejects the reserved table name
`Measures`.

Relationships are limited to observation-to-measurement and
sensor-to-measurement, both active, one-to-many, and single-direction. The
version and measure tables are disconnected. Auto date/time is disabled,
model culture and source-query culture are `en-US`, and implicit measures are
discouraged.

Missing values remain BLANK; there is no imputation. SMD uses pass/fail means,
sample variance (`VAR.S`), and degrees-of-freedom-weighted pooled variance. Its
sign only indicates whether the fail mean is above or below the pass mean.
Rank measures break ties by ascending sensor index.

## Reconciliation and evidence

The refreshed model contains:

- one canonical dataset version;
- 1,567 observations;
- 590 sensors;
- 924,530 measurement coordinates;
- 41,951 missing coordinates;
- 1,463 pass observations and 104 fail observations.

The six saved DAX queries cover provenance, load reconciliation, outcome
distribution, daily yield, all-sensor missingness, and all-sensor SMD. Desktop
2.156.951.0 emits an exact English RFC date/time representation and emits BLANK
for certain grouped zero measures. The normalizer therefore recognizes only
the explicitly authorized RFC syntax, while DAX queries 05 and 07 use
`COALESCE(..., 0)` solely on the affected outputs.

Normalized row counts are 1, 1, 2, 86, 590, and 590. All rows matched both the
corresponding read-only PostgreSQL query and calculations made directly from
`quality-report.json`, `secom.data`, and `secom_labels.data`, using
`rel_tol=1e-9` and `abs_tol=1e-12`. There are 474 calculable SMD values and 116
NULL values. IDs and the exact load timestamp are not retained in versioned
evidence.

## Security

Power BI authenticates only as `qualityops_powerbi_reader`. The role has no
ownership, memberships, write privileges, schema creation, temporary-table
privilege, grant option, or predefined privileged role. It can connect, use
`qualityops`, and select only `dataset`, `dataset_version`, `observation`,
`sensor`, and `measurement`. It cannot read `source_file`,
`v_measurement_fact`, or Alembic state.

Administrator authority creates and drops the temporary role. Database-owner
authority hardens PUBLIC ACLs and grants or revokes application access. The
password and reader connection URL remain transient environment values and are
not command-line arguments, files, logs, PBIP parameters, or documentation.

## Page layout, accessibility, and render evidence

The 1280 × 720 canvas contains one title, one reconciliation card, five KPI
cards, four native charts, and one footer. Visible labels, non-color status
text, 4.5:1 contrast, non-empty alt text, keyboard tab order 1–10,
deterministic Top 10 filters, and all 90 pairwise interactions set to `None`
were validated. The project reopened and rendered in the frozen Desktop build.
The canvas-only file `docs/assets/powerbi-process-health.png` is an authentic
Desktop Bridge capture with the filter pane and exterior workspace cropped
away; no report content was recreated.

The official authoring validator reports `PBIR_SCHEMA_UNREACHABLE` because its
schema fetch for the build-generated `visualContainer/2.11.0` URL is
unavailable. Validation otherwise reports zero errors, and Desktop 2.156.951.0
accepts and renders the files. The two native ranking charts necessarily show
an internal scrollbar at the contractual height. The static preview shows the
initial viewport, while the DAX grids, visual Top 10 filters, rank ordering,
and tests establish the complete ten-member sets. Neither limitation expands
the evidence or implies production support.

## Interpretive limits

The report does not establish production readiness, real-time operation,
process stability, specification-based capability, root causes, prediction,
machine learning, automated recommendations, savings, MES/QMS integration, or
industrial scalability. It is not published to Power BI Service or Fabric.

## Licensing

Project-authored M, DAX, TMDL, PBIR, Python, SQL, theme, and documentation are
MIT. The normalized TSV evidence, validation summary, screenshot, and any other
SECOM-derived representation remain CC BY 4.0 with visible UCI attribution.
