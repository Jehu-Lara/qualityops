SELECT
    m.dataset_version_id,
    m.sensor_index,
    s.sensor_key,
    COUNT(m.value) AS nonmissing_count,
    COUNT(DISTINCT m.value) FILTER (WHERE m.value IS NOT NULL) AS distinct_nonmissing_count,
    MIN(m.value) AS constant_value
FROM qualityops.measurement AS m
JOIN qualityops.sensor AS s
  ON s.dataset_version_id = m.dataset_version_id
 AND s.sensor_index = m.sensor_index
WHERE m.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
GROUP BY m.dataset_version_id, m.sensor_index, s.sensor_key
HAVING COUNT(m.value) > 0
   AND COUNT(DISTINCT m.value) FILTER (WHERE m.value IS NOT NULL) = 1
ORDER BY m.sensor_index;
