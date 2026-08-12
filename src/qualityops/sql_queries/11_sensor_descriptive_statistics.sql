SELECT
    m.dataset_version_id,
    m.sensor_index,
    s.sensor_key,
    COUNT(*) AS measurement_count,
    COUNT(m.value) AS nonmissing_count,
    COUNT(*) FILTER (WHERE m.value IS NULL) AS missing_count,
    MIN(m.value) AS minimum_value,
    MAX(m.value) AS maximum_value,
    AVG(m.value) AS mean_value,
    stddev_samp(m.value) AS sample_stddev
FROM qualityops.measurement AS m
JOIN qualityops.sensor AS s
  ON s.dataset_version_id = m.dataset_version_id
 AND s.sensor_index = m.sensor_index
WHERE m.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
GROUP BY m.dataset_version_id, m.sensor_index, s.sensor_key
ORDER BY m.sensor_index;
