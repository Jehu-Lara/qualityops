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
        AS owner_valid,
    EXISTS (
        SELECT 1
        FROM pg_namespace
        WHERE nspname = 'qualityops'
          AND pg_get_userbyid(nspowner) = :'expected_owner'
    ) AS schema_valid
FROM pg_database AS d
WHERE d.datname = current_database()
\gset

\if :database_valid
\else
  \echo 'Refusing to harden a non-contractual database' >&2
  \quit 3
\endif
\if :owner_valid
\else
  \echo 'The current user or database owner is not contractual' >&2
  \quit 3
\endif
\if :schema_valid
\else
  \echo 'The qualityops schema owner is not contractual' >&2
  \quit 3
\endif

BEGIN;
REVOKE CONNECT, CREATE, TEMPORARY ON DATABASE :"expected_database" FROM PUBLIC;
REVOKE CREATE, USAGE ON SCHEMA public FROM PUBLIC;
REVOKE ALL PRIVILEGES ON SCHEMA qualityops FROM PUBLIC;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA qualityops FROM PUBLIC;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA qualityops FROM PUBLIC;
REVOKE ALL PRIVILEGES ON ALL ROUTINES IN SCHEMA qualityops FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE :"expected_owner" IN SCHEMA qualityops
    REVOKE ALL PRIVILEGES ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE :"expected_owner" IN SCHEMA qualityops
    REVOKE ALL PRIVILEGES ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE :"expected_owner" IN SCHEMA qualityops
    REVOKE ALL PRIVILEGES ON ROUTINES FROM PUBLIC;
COMMIT;
