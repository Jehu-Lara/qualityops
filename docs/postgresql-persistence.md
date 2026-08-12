# PostgreSQL persistence

## Status and architecture

This alpha portfolio milestone persists the verified public UCI SECOM dataset
in PostgreSQL 16. It is not a production deployment or a capacity benchmark.
The schema is normalized rather than a 590-column wide table:

```text
dataset ──< dataset_version ──< source_file
                         ├────< observation ──< measurement
                         └────< sensor ───────< measurement
```

`source_row` is the physical one-based source row. `sensor_index` is the
physical zero-based measurement column. The composite foreign keys on
`measurement` prevent observations and sensors from crossing dataset versions;
source `NaN` is stored as SQL `NULL` without imputation.

## Migration and rollback

Alembic owns the `qualityops` schema and keeps its single revision in
`public.alembic_version`:

```powershell
$env:QUALITYOPS_DATABASE_URL='<Psycopg-compatible PostgreSQL URL>'
python -m alembic upgrade head
python -m alembic downgrade base
```

The upgrade deliberately uses `CREATE SCHEMA qualityops` without
`IF NOT EXISTS`; it refuses to adopt an existing schema. The downgrade drops
only named contract objects and finishes with `DROP SCHEMA qualityops` without
`CASCADE`, so an unexpected object blocks and rolls back the downgrade.

## Loader operation

```powershell
$env:QUALITYOPS_DATABASE_URL='<Psycopg-compatible PostgreSQL URL>'
qualityops load-secom-postgres --data-dir data/external/secom
```

Before connecting, the loader verifies the canonical report schema, exact raw
filenames, sizes, acquisition hashes, fingerprint, complete parsing and all
numeric quality oracles. After connecting, it checks the exact Alembic head and
then takes a stable transaction-scoped advisory lock for `uci-secom`.

Dataset resolution, conflict checks, inserts, `COPY`, reconciliation and commit
use one Psycopg connection and transaction. Any exception rolls back all six
tables. A matching second load validates every persisted business field and all
924,530 measurements in deterministic batches, performs no DML or `COPY`, and
returns `already_loaded`. A different label, fingerprint, relationship,
manifest row or persisted value is a conflict; the loader never repairs data
and never uses `ON CONFLICT`.

Concurrent loads serialize on the dataset lock. Exactly one can create the
canonical version; a later waiter validates it and returns `already_loaded`.

## Read-only analytical queries

The twenty files under `sql/queries/` are executed with SQLAlchemy `text()` in
a streaming, read-only transaction. Callers must consume mappings or
`fetchmany()` inside `stream_quality_query(...)`; the context closes the result,
rolls back the read-only transaction and closes the connection. Query 20 must
use batches and must not call `fetchall()`.

See [the query contract](../sql/queries/README.md) for parameters, columns,
units, statistical semantics, NULL cases and deterministic ordering.

## Integration verification

Use only a dedicated disposable database owned by `qualityops_test_owner` and
named `qualityops_test_*`. PostgreSQL 16 real is mandatory.

Después de definir `QUALITYOPS_TEST_DATABASE_URL`:

```powershell
$env:QUALITYOPS_RUN_POSTGRES_INTEGRATION='1'
.\.venv\Scripts\python.exe -m unittest -v tests.test_postgres_integration
```

The harness rejects a missing or unsafe DSN, verifies the server and owner,
exercises upgrade/downgrade, constraints, rollback after partial `COPY`, all
corruption families, deterministic concurrency and all twenty queries. With
integration active, any skipped test fails the suite.

## Limits

SECOM supplies no specification limits or documented within-subgroup sigma, so
the persistence layer does not establish `Cp`, `Cpk`, `Pp` or `Ppk`. It does
not demonstrate causality, production readiness, industrial capacity,
scalability, Power BI, FastAPI, ML or AI.
