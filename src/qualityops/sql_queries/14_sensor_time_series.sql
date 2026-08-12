SELECT
    f.dataset_version_id,
    f.sensor_index,
    f.sensor_key,
    f.source_row,
    f.observed_at,
    f.outcome,
    f.outcome_name,
    f.value,
    f.is_missing
FROM qualityops.v_measurement_fact AS f
WHERE f.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
  AND f.sensor_key = CAST(:sensor_key AS TEXT)
  AND f.observed_at >= CAST(:start_at AS TIMESTAMP WITHOUT TIME ZONE)
  AND f.observed_at < CAST(:end_at AS TIMESTAMP WITHOUT TIME ZONE)
ORDER BY f.observed_at, f.source_row;
