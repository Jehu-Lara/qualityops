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
\gset

\if :database_valid
\else
  \echo 'The target database or owner is not contractual' >&2
  \quit 3
\endif
\if :administrator_valid
\else
  \echo 'The current user cannot drop roles' >&2
  \quit 3
\endif
\if :reader_valid
\else
  \echo 'The reader role is absent or has unexpected attributes' >&2
  \quit 3
\endif
\if :memberships_clear
\else
  \echo 'The reader role has unexpected memberships' >&2
  \quit 3
\endif

DROP ROLE qualityops_powerbi_reader;
