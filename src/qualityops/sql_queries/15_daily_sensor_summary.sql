SELECT
    f.dataset_version_id,
    f.sensor_index,
    f.sensor_key,
    CAST(f.observed_at AS DATE) AS observed_date,
    COUNT(*) AS measurement_count,
    COUNT(f.value) AS nonmissing_count,
    COUNT(*) FILTER (WHERE f.value IS NULL) AS missing_count,
    MIN(f.value) AS minimum_value,
    MAX(f.value) AS maximum_value,
    AVG(f.value) AS mean_value,
    stddev_samp(f.value) AS sample_stddev
FROM qualityops.v_measurement_fact AS f
WHERE f.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
  AND f.sensor_key = CAST(:sensor_key AS TEXT)
GROUP BY f.dataset_version_id, f.sensor_index, f.sensor_key, CAST(f.observed_at AS DATE)
ORDER BY observed_date;
