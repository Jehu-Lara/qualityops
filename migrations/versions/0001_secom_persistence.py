"""Create the normalized, auditable SECOM persistence schema.

Revision ID: 0001_secom_persistence
Revises: None
"""

from __future__ import annotations

from alembic import op


revision = "0001_secom_persistence"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA qualityops")
    op.execute(
        """
        CREATE TABLE qualityops.dataset (
            dataset_id BIGINT GENERATED ALWAYS AS IDENTITY NOT NULL,
            dataset_code TEXT NOT NULL,
            name TEXT NOT NULL,
            publisher TEXT NOT NULL,
            doi TEXT NULL,
            source_url TEXT NOT NULL,
            license_spdx TEXT NOT NULL,
            CONSTRAINT pk_dataset PRIMARY KEY (dataset_id),
            CONSTRAINT uq_dataset_dataset_code UNIQUE (dataset_code),
            CONSTRAINT uq_dataset_doi UNIQUE (doi),
            CONSTRAINT ck_dataset_dataset_code_nonempty CHECK (btrim(dataset_code) <> ''),
            CONSTRAINT ck_dataset_name_nonempty CHECK (btrim(name) <> ''),
            CONSTRAINT ck_dataset_publisher_nonempty CHECK (btrim(publisher) <> ''),
            CONSTRAINT ck_dataset_doi_nonempty CHECK (doi IS NULL OR btrim(doi) <> ''),
            CONSTRAINT ck_dataset_source_url_https CHECK (source_url ~ '^https://[^[:space:]]+$'),
            CONSTRAINT ck_dataset_license_spdx_nonempty CHECK (btrim(license_spdx) <> '')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE qualityops.dataset_version (
            dataset_version_id BIGINT GENERATED ALWAYS AS IDENTITY NOT NULL,
            dataset_id BIGINT NOT NULL,
            version_label TEXT NOT NULL,
            content_fingerprint CHAR(64) NOT NULL,
            acquired_on DATE NOT NULL,
            loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            audit_schema_version SMALLINT NOT NULL,
            observation_count INTEGER NOT NULL,
            sensor_count SMALLINT NOT NULL,
            measurement_count INTEGER NOT NULL,
            missing_measurement_count INTEGER NOT NULL,
            CONSTRAINT pk_dataset_version PRIMARY KEY (dataset_version_id),
            CONSTRAINT fk_dataset_version_dataset FOREIGN KEY (dataset_id)
                REFERENCES qualityops.dataset(dataset_id) ON DELETE RESTRICT,
            CONSTRAINT uq_dataset_version_dataset_version_label
                UNIQUE (dataset_id, version_label),
            CONSTRAINT uq_dataset_version_dataset_fingerprint
                UNIQUE (dataset_id, content_fingerprint),
            CONSTRAINT ck_dataset_version_label_nonempty CHECK (btrim(version_label) <> ''),
            CONSTRAINT ck_dataset_version_fingerprint_sha256
                CHECK (content_fingerprint ~ '^[0-9A-F]{64}$'),
            CONSTRAINT ck_dataset_version_audit_schema_version_positive
                CHECK (audit_schema_version > 0),
            CONSTRAINT ck_dataset_version_observation_count_positive
                CHECK (observation_count > 0),
            CONSTRAINT ck_dataset_version_sensor_count_positive
                CHECK (sensor_count > 0),
            CONSTRAINT ck_dataset_version_measurement_count_positive
                CHECK (measurement_count > 0),
            CONSTRAINT ck_dataset_version_measurement_count_consistent
                CHECK (measurement_count = observation_count * sensor_count),
            CONSTRAINT ck_dataset_version_missing_count_range
                CHECK (missing_measurement_count >= 0
                       AND missing_measurement_count <= measurement_count)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE qualityops.source_file (
            dataset_version_id BIGINT NOT NULL,
            filename TEXT NOT NULL,
            role TEXT NOT NULL,
            byte_size BIGINT NOT NULL,
            sha256 CHAR(64) NOT NULL,
            CONSTRAINT pk_source_file PRIMARY KEY (dataset_version_id, filename),
            CONSTRAINT fk_source_file_dataset_version FOREIGN KEY (dataset_version_id)
                REFERENCES qualityops.dataset_version(dataset_version_id) ON DELETE CASCADE,
            CONSTRAINT uq_source_file_dataset_version_role UNIQUE (dataset_version_id, role),
            CONSTRAINT ck_source_file_filename_nonempty CHECK (btrim(filename) <> ''),
            CONSTRAINT ck_source_file_role
                CHECK (role IN ('measurements', 'labels', 'metadata')),
            CONSTRAINT ck_source_file_byte_size_positive CHECK (byte_size > 0),
            CONSTRAINT ck_source_file_sha256 CHECK (sha256 ~ '^[0-9A-F]{64}$')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE qualityops.observation (
            dataset_version_id BIGINT NOT NULL,
            source_row INTEGER NOT NULL,
            observed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            outcome SMALLINT NOT NULL,
            CONSTRAINT pk_observation PRIMARY KEY (dataset_version_id, source_row),
            CONSTRAINT fk_observation_dataset_version FOREIGN KEY (dataset_version_id)
                REFERENCES qualityops.dataset_version(dataset_version_id) ON DELETE CASCADE,
            CONSTRAINT ck_observation_source_row_positive CHECK (source_row > 0),
            CONSTRAINT ck_observation_outcome CHECK (outcome IN (-1, 1))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE qualityops.sensor (
            dataset_version_id BIGINT NOT NULL,
            sensor_index SMALLINT NOT NULL,
            sensor_key TEXT NOT NULL,
            CONSTRAINT pk_sensor PRIMARY KEY (dataset_version_id, sensor_index),
            CONSTRAINT fk_sensor_dataset_version FOREIGN KEY (dataset_version_id)
                REFERENCES qualityops.dataset_version(dataset_version_id) ON DELETE CASCADE,
            CONSTRAINT uq_sensor_dataset_version_sensor_key
                UNIQUE (dataset_version_id, sensor_key),
            CONSTRAINT ck_sensor_index_range CHECK (sensor_index BETWEEN 0 AND 589),
            CONSTRAINT ck_sensor_key_matches_index CHECK (
                sensor_key = 'sensor_' || lpad(sensor_index::text, 3, '0')
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE qualityops.measurement (
            dataset_version_id BIGINT NOT NULL,
            source_row INTEGER NOT NULL,
            sensor_index SMALLINT NOT NULL,
            value DOUBLE PRECISION NULL,
            CONSTRAINT pk_measurement
                PRIMARY KEY (dataset_version_id, source_row, sensor_index),
            CONSTRAINT fk_measurement_observation
                FOREIGN KEY (dataset_version_id, source_row)
                REFERENCES qualityops.observation(dataset_version_id, source_row)
                ON DELETE CASCADE,
            CONSTRAINT fk_measurement_sensor
                FOREIGN KEY (dataset_version_id, sensor_index)
                REFERENCES qualityops.sensor(dataset_version_id, sensor_index)
                ON DELETE CASCADE,
            CONSTRAINT ck_measurement_finite CHECK (
                value IS NULL OR value NOT IN (
                    'NaN'::double precision,
                    'Infinity'::double precision,
                    '-Infinity'::double precision
                )
            )
        )
        """
    )
    op.execute(
        """CREATE INDEX ix_observation_version_observed_at
           ON qualityops.observation (dataset_version_id, observed_at)"""
    )
    op.execute(
        """CREATE INDEX ix_observation_version_outcome_observed_at
           ON qualityops.observation (dataset_version_id, outcome, observed_at)"""
    )
    op.execute(
        """CREATE INDEX ix_measurement_version_sensor_source_row
           ON qualityops.measurement (dataset_version_id, sensor_index, source_row)
           INCLUDE (value)"""
    )
    op.execute(
        """CREATE INDEX ix_measurement_missing_by_observation
           ON qualityops.measurement (dataset_version_id, source_row)
           WHERE value IS NULL"""
    )
    op.execute(
        """
        CREATE VIEW qualityops.v_measurement_fact AS
        SELECT
            m.dataset_version_id,
            m.source_row,
            o.observed_at,
            o.outcome,
            CASE o.outcome WHEN -1 THEN 'pass' WHEN 1 THEN 'fail' END AS outcome_name,
            m.sensor_index,
            s.sensor_key,
            m.value,
            (m.value IS NULL) AS is_missing
        FROM qualityops.measurement AS m
        JOIN qualityops.observation AS o
          ON o.dataset_version_id = m.dataset_version_id
         AND o.source_row = m.source_row
        JOIN qualityops.sensor AS s
          ON s.dataset_version_id = m.dataset_version_id
         AND s.sensor_index = m.sensor_index
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW qualityops.v_measurement_fact")
    op.execute("DROP INDEX qualityops.ix_measurement_missing_by_observation")
    op.execute("DROP INDEX qualityops.ix_measurement_version_sensor_source_row")
    op.execute("DROP INDEX qualityops.ix_observation_version_outcome_observed_at")
    op.execute("DROP INDEX qualityops.ix_observation_version_observed_at")
    op.execute("DROP TABLE qualityops.measurement")
    op.execute("DROP TABLE qualityops.sensor")
    op.execute("DROP TABLE qualityops.observation")
    op.execute("DROP TABLE qualityops.source_file")
    op.execute("DROP TABLE qualityops.dataset_version")
    op.execute("DROP TABLE qualityops.dataset")
    op.execute("DROP SCHEMA qualityops")
