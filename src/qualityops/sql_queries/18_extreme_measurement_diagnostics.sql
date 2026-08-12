WITH sensor_statistics AS (
    SELECT
        m.dataset_version_id,
        m.sensor_index,
        s.sensor_key,
        COUNT(m.value) AS sample_count,
        AVG(m.value) AS mean_value,
        stddev_samp(m.value) AS sample_stddev
    FROM qualityops.measurement AS m
    JOIN qualityops.sensor AS s
      ON s.dataset_version_id = m.dataset_version_id
     AND s.sensor_index = m.sensor_index
    WHERE m.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
    GROUP BY m.dataset_version_id, m.sensor_index, s.sensor_key
), extremes AS (
    SELECT
        ss.dataset_version_id,
        ss.sensor_index,
        ss.sensor_key,
        CAST('extreme' AS TEXT) AS row_kind,
        CAST(NULL AS TEXT) AS reason,
        ss.sample_count,
        ss.sample_stddev,
        m.source_row,
        o.observed_at,
        o.outcome,
        m.value,
        (m.value - ss.mean_value) / ss.sample_stddev AS z_score,
        CAST(:z_threshold AS DOUBLE PRECISION) AS z_threshold
    FROM sensor_statistics AS ss
    JOIN qualityops.measurement AS m
      ON m.dataset_version_id = ss.dataset_version_id
     AND m.sensor_index = ss.sensor_index
    JOIN qualityops.observation AS o
      ON o.dataset_version_id = m.dataset_version_id
     AND o.source_row = m.source_row
    WHERE ss.sample_count >= 2
      AND ss.sample_stddev IS NOT NULL
      AND ss.sample_stddev > 0
      AND abs((m.value - ss.mean_value) / ss.sample_stddev)
          >= CAST(:z_threshold AS DOUBLE PRECISION)
), unscorable AS (
    SELECT
        ss.dataset_version_id,
        ss.sensor_index,
        ss.sensor_key,
        CAST('unscorable' AS TEXT) AS row_kind,
        CASE
            WHEN ss.sample_count < 2 THEN 'insufficient_sample'
            ELSE 'nonpositive_variance'
        END AS reason,
        ss.sample_count,
        ss.sample_stddev,
        CAST(NULL AS INTEGER) AS source_row,
        CAST(NULL AS TIMESTAMP WITHOUT TIME ZONE) AS observed_at,
        CAST(NULL AS SMALLINT) AS outcome,
        CAST(NULL AS DOUBLE PRECISION) AS value,
        CAST(NULL AS DOUBLE PRECISION) AS z_score,
        CAST(:z_threshold AS DOUBLE PRECISION) AS z_threshold
    FROM sensor_statistics AS ss
    WHERE ss.sample_count < 2
       OR ss.sample_stddev IS NULL
       OR ss.sample_stddev <= 0
)
SELECT
    e.dataset_version_id,
    e.sensor_index,
    e.sensor_key,
    e.row_kind,
    e.reason,
    e.sample_count,
    e.sample_stddev,
    e.source_row,
    e.observed_at,
    e.outcome,
    e.value,
    e.z_score,
    e.z_threshold
FROM extremes AS e
UNION ALL
SELECT
    u.dataset_version_id,
    u.sensor_index,
    u.sensor_key,
    u.row_kind,
    u.reason,
    u.sample_count,
    u.sample_stddev,
    u.source_row,
    u.observed_at,
    u.outcome,
    u.value,
    u.z_score,
    u.z_threshold
FROM unscorable AS u
ORDER BY sensor_index, row_kind, source_row NULLS FIRST;
