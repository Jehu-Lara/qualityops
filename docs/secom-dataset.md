# UCI SECOM dataset provenance and quality record

## Purpose and source

QualityOps versions the original SECOM files to provide a reproducible,
auditable example of real external manufacturing data. Michael McCann and
Adrian Johnston donated SECOM to the UCI Machine Learning Repository in 2008.
The dataset represents measurements from a semiconductor manufacturing process
with an associated in-house line-test outcome.

- Canonical record: https://archive.ics.uci.edu/dataset/179/secom
- DOI: https://doi.org/10.24432/C54305
- Creators: Michael McCann and Adrian Johnston
- License: Creative Commons Attribution 4.0 International (CC BY 4.0)
- Acquisition date: 2026-08-10
- Acquisition URL: https://archive.ics.uci.edu/static/public/179/secom.zip

The QualityOps code remains MIT-licensed. The three original SECOM files retain
CC BY 4.0 and are not relicensed under the repository's MIT license.
Representations derived from SECOM data, including persisted measurements and
quality reports, also retain CC BY 4.0. Python code, Alembic migrations and SQL
query code remain MIT-licensed.

## Acquisition and integrity

The archive was downloaded directly from the UCI acquisition URL, hashed,
extracted without modification, and inspected locally. The archive itself is
not committed. The extracted files are committed byte-for-byte and protected
from Git text normalization by `.gitattributes`.

These are hashes verified by QualityOps during acquisition. They are not
described as official hashes published by UCI.

| Artifact | Size (bytes) | SHA-256 acquired |
|---|---:|---|
| `secom.zip` | 1,964,989 | `EEA568BAF3C2229096D7D294CF0B096B5502BD96D92C0B80A65B84714059BE8E` |
| `secom.data` | 5,389,983 | `20F0E7EE434F7DCBAE0EEA9FFFF009A2B57F42D6B0DC9A5BD4F00782C0A3374C` |
| `secom_labels.data` | 40,638 | `126884CF453705C9E61A903FE906F0665A3B45CE3639E621EDC5C93C89627E03` |
| `secom.names` | 4,223 | `6D91B0B46CDEE03064EE3E3112F937C1B3F7FCD9933575794EC07974E6F1EA59` |

`qualityops audit-secom --data-dir data/external/secom/raw` verifies the three
extracted files before parsing them. The ZIP hash is retained only as part of
the acquisition record.

`qualityops load-secom-postgres --data-dir data/external/secom` uses the same
three verified files and the committed `quality-report.json`. It maps physical
one-based rows to `observation.source_row`, zero-based measurement columns to
`sensor.sensor_index`, and every row/column coordinate to the normalized
`measurement` table. No imputation occurs: source `NaN` becomes SQL `NULL`.

## Structure and source semantics

- `secom.data` contains 1,567 rows and 590 measurement columns.
- `secom_labels.data` contains one label and timestamp for every measurement
  row.
- Label `-1` means pass and label `1` means fail.
- `NaN` represents a missing measurement.
- Timestamps use `DD/MM/YYYY HH:MM:SS` in the source.

UCI announces 591 characteristics, while `secom.data` contains 590 columns of
measurements. The label and timestamp are stored separately in
`secom_labels.data`. QualityOps preserves this metadata discrepancy without
inventing a signal number 591.

## Reproducible quality results

The committed `data/external/secom/quality-report.json` contains every
per-sensor missing count and the complete ordered list of constant sensors.
Its principal results are:

| Metric | Result |
|---|---:|
| Rows | 1,567 |
| Measurement sensors | 590 |
| Missing measurement cells | 41,951 |
| Sensors with missing values | 538 |
| Entirely missing sensors | 0 |
| Constant sensors | 116 |
| Duplicate records, excluding generated `source_row` | 0 |
| Pass labels (`-1`) | 1,463 |
| Fail labels (`1`) | 104 |
| Invalid timestamps | 0 |
| Timestamp occurrences after the first | 33 |
| Distinct timestamp values that repeat | 32 |
| Earliest timestamp | `2008-07-19T11:55:00` |
| Latest timestamp | `2008-10-17T06:07:00` |

Duplicate records compare timestamp, label, and all 590 sensors, exclude the
generated 1-based `source_row`, and treat missing values in corresponding
positions as equivalent. A sensor is constant only when
`nunique(dropna=True) == 1`.

## Interpretation limits

SECOM does not provide documented lower or upper specification limits or a
within-subgroup standard-deviation estimate. QualityOps therefore does not use
it to report or claim `Cp`, `Cpk`, `Pp`, or `Ppk`. The dataset also does not by
itself establish process stability, measurement-system adequacy, causal
drivers, production readiness, or production deployment.

The current audit is deterministic Python data processing. It is not an AI
analysis, and no model is allowed to invent or replace the reported figures.
