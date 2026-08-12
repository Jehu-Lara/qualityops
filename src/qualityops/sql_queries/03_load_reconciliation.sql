WITH actual AS (
    SELECT
        dv.dataset_version_id,
        (SELECT COUNT(*) FROM qualityops.observation AS o
         WHERE o.dataset_version_id = dv.dataset_version_id) AS actual_observation_count,
        (SELECT COUNT(*) FROM qualityops.sensor AS s
         WHERE s.dataset_version_id = dv.dataset_version_id) AS actual_sensor_count,
        (SELECT COUNT(*) FROM qualityops.measurement AS m
         WHERE m.dataset_version_id = dv.dataset_version_id) AS actual_measurement_count,
        (SELECT COUNT(*) FROM qualityops.measurement AS m
         WHERE m.dataset_version_id = dv.dataset_version_id
           AND m.value IS NULL) AS actual_missing_measurement_count,
        NOT EXISTS (
            SELECT 1
            FROM qualityops.observation AS o
            LEFT JOIN qualityops.measurement AS m
              ON m.dataset_version_id = o.dataset_version_id
             AND m.source_row = o.source_row
            WHERE o.dataset_version_id = dv.dataset_version_id
            GROUP BY o.source_row
            HAVING COUNT(m.sensor_index) <> dv.sensor_count
        ) AS measurements_per_observation_match
    FROM qualityops.dataset_version AS dv
    WHERE dv.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
)
SELECT
    dv.dataset_version_id,
    dv.observation_count AS expected_observation_count,
    a.actual_observation_count,
    (dv.observation_count = a.actual_observation_count) AS observations_match,
    dv.sensor_count AS expected_sensor_count,
    a.actual_sensor_count,
    (dv.sensor_count = a.actual_sensor_count) AS sensors_match,
    dv.measurement_count AS expected_measurement_count,
    a.actual_measurement_count,
    (dv.measurement_count = a.actual_measurement_count) AS measurements_match,
    dv.missing_measurement_count AS expected_missing_measurement_count,
    a.actual_missing_measurement_count,
    (dv.missing_measurement_count = a.actual_missing_measurement_count) AS missing_measurements_match,
    a.measurements_per_observation_match
FROM qualityops.dataset_version AS dv
JOIN actual AS a
  ON a.dataset_version_id = dv.dataset_version_id
ORDER BY dv.dataset_version_id;
