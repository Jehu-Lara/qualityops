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
        FROM pg_roles
        WHERE rolname = 'qualityops_powerbi_reader'
          AND rolcanlogin
          AND NOT rolsuper
          AND NOT rolcreatedb
          AND NOT rolcreaterole
          AND NOT rolinherit
          AND NOT rolreplication
          AND NOT rolbypassrls
          AND rolconnlimit = 5
    ) AS reader_valid,
    NOT EXISTS (
        SELECT 1
        FROM pg_auth_members AS m
        JOIN pg_roles AS member_role ON member_role.oid = m.member
        JOIN pg_roles AS granted_role ON granted_role.oid = m.roleid
        WHERE member_role.rolname = 'qualityops_powerbi_reader'
           OR granted_role.rolname = 'qualityops_powerbi_reader'
    ) AS memberships_clear
FROM pg_database AS d
WHERE d.datname = current_database()
\gset

\if :database_valid
\else
  \echo 'Refusing grants in a non-contractual database' >&2
  \quit 3
\endif
\if :owner_valid
\else
  \echo 'The current user or database owner is not contractual' >&2
  \quit 3
\endif
\if :reader_valid
\else
  \echo 'The reader role attributes are not contractual' >&2
  \quit 3
\endif
\if :memberships_clear
\else
  \echo 'The reader role has unexpected memberships' >&2
  \quit 3
\endif

BEGIN;
GRANT CONNECT ON DATABASE :"expected_database" TO qualityops_powerbi_reader;
GRANT USAGE ON SCHEMA qualityops TO qualityops_powerbi_reader;
GRANT SELECT ON TABLE
    qualityops.dataset,
    qualityops.dataset_version,
    qualityops.observation,
    qualityops.sensor,
    qualityops.measurement
TO qualityops_powerbi_reader;
COMMIT;
