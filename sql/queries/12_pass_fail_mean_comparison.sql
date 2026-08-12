SELECT
    m.dataset_version_id,
    m.sensor_index,
    s.sensor_key,
    COUNT(m.value) FILTER (WHERE o.outcome = -1) AS pass_count,
    AVG(m.value) FILTER (WHERE o.outcome = -1) AS pass_mean,
    COUNT(m.value) FILTER (WHERE o.outcome = 1) AS fail_count,
    AVG(m.value) FILTER (WHERE o.outcome = 1) AS fail_mean,
    AVG(m.value) FILTER (WHERE o.outcome = 1)
        - AVG(m.value) FILTER (WHERE o.outcome = -1) AS fail_minus_pass_mean
FROM qualityops.measurement AS m
JOIN qualityops.observation AS o
  ON o.dataset_version_id = m.dataset_version_id
 AND o.source_row = m.source_row
JOIN qualityops.sensor AS s
  ON s.dataset_version_id = m.dataset_version_id
 AND s.sensor_index = m.sensor_index
WHERE m.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
GROUP BY m.dataset_version_id, m.sensor_index, s.sensor_key
ORDER BY m.sensor_index;
