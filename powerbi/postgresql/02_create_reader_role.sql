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

\getenv reader_password QUALITYOPS_POWERBI_READER_PASSWORD
\if :{?reader_password}
\else
  \echo 'QUALITYOPS_POWERBI_READER_PASSWORD is required' >&2
  \quit 3
\endif

SELECT
    :'expected_database' ~ '^qualityops_test_[a-z0-9_]+$'
        AND :'expected_database' NOT IN ('postgres', 'template0', 'template1')
        AND EXISTS (
            SELECT 1
            FROM pg_database
            WHERE datname = :'expected_database'
              AND pg_get_userbyid(datdba) = :'expected_owner'
        ) AS database_valid,
    EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = current_user
          AND (rolsuper OR rolcreaterole)
    ) AS administrator_valid,
    NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'qualityops_powerbi_reader'
    ) AS reader_absent,
    length(:'reader_password') >= 32
        AND :'reader_password' ~ '^[0-9A-Fa-f]+$' AS password_valid
\gset

\if :database_valid
\else
  \echo 'The target database or owner is not contractual' >&2
  \quit 3
\endif
\if :administrator_valid
\else
  \echo 'The current user cannot create roles' >&2
  \quit 3
\endif
\if :reader_absent
\else
  \echo 'qualityops_powerbi_reader already exists' >&2
  \quit 3
\endif
\if :password_valid
\else
  \echo 'The reader password must be at least 32 hexadecimal characters' >&2
  \quit 3
\endif

BEGIN;
SET LOCAL password_encryption = 'scram-sha-256';
CREATE ROLE qualityops_powerbi_reader
    LOGIN
    PASSWORD :'reader_password'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    NOBYPASSRLS
    CONNECTION LIMIT 5;
ALTER ROLE qualityops_powerbi_reader
    IN DATABASE :"expected_database"
    SET search_path TO pg_catalog, qualityops;
COMMIT;
