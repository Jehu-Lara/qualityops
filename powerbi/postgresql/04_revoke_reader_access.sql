\set ON_ERROR_STOP on

\if :{?expected_database}
\else
  \echo 'expected_database is required' >&2
  \quit 3
\endif
\if :{?expected_owner}
\else
  \echo 'expected_owner is required' >&2
  \quit 3
\endif

SELECT
    current_database() = :'expected_database'
        AND :'expected_database' ~ '^qualityops_test_[a-z0-9_]+$'
        AND :'expected_database' NOT IN ('postgres', 'template0', 'template1')
        AS database_valid,
    current_user = :'expected_owner'
        AND pg_get_userbyid(d.datdba) = :'expected_owner'
        AS owner_valid
FROM pg_database AS d
WHERE d.datname = current_database()
\gset

\if :database_valid
\else
  \echo 'Refusing revocation in a non-contractual database' >&2
  \quit 3
\endif
\if :owner_valid
\else
  \echo 'The current user or database owner is not contractual' >&2
  \quit 3
\endif

SELECT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'qualityops_powerbi_reader'
) AS reader_exists,
EXISTS (
    SELECT 1 FROM pg_namespace WHERE nspname = 'qualityops'
) AS qualityops_schema_exists,
to_regclass('qualityops.dataset') IS NOT NULL
    AND to_regclass('qualityops.dataset_version') IS NOT NULL
    AND to_regclass('qualityops.observation') IS NOT NULL
    AND to_regclass('qualityops.sensor') IS NOT NULL
    AND to_regclass('qualityops.measurement') IS NOT NULL
    AS reader_relations_exist
\gset

\if :reader_exists
BEGIN;
\if :reader_relations_exist
REVOKE SELECT ON TABLE
    qualityops.dataset,
    qualityops.dataset_version,
    qualityops.observation,
    qualityops.sensor,
    qualityops.measurement
FROM qualityops_powerbi_reader;
\endif
\if :qualityops_schema_exists
REVOKE USAGE ON SCHEMA qualityops FROM qualityops_powerbi_reader;
\endif
REVOKE CONNECT ON DATABASE :"expected_database" FROM qualityops_powerbi_reader;
COMMIT;
\endif
