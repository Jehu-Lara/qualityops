SELECT
    f.dataset_version_id,
    f.source_row,
    f.observed_at,
    f.outcome,
    f.outcome_name,
    f.sensor_index,
    f.sensor_key,
    f.value,
    f.is_missing
FROM qualityops.v_measurement_fact AS f
WHERE f.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
  AND f.source_row = CAST(:source_row AS INTEGER)
ORDER BY f.sensor_index;
