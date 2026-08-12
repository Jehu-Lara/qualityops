SELECT
    m.dataset_version_id,
    m.sensor_index,
    s.sensor_key,
    o.outcome,
    CASE o.outcome WHEN -1 THEN 'pass' WHEN 1 THEN 'fail' END AS outcome_name,
    COUNT(*) AS observation_count,
    COUNT(m.value) AS nonmissing_count,
    COUNT(*) FILTER (WHERE m.value IS NULL) AS missing_count,
    COUNT(*) FILTER (WHERE m.value IS NULL)::DOUBLE PRECISION / COUNT(*) AS missing_rate
FROM qualityops.measurement AS m
JOIN qualityops.observation AS o
  ON o.dataset_version_id = m.dataset_version_id
 AND o.source_row = m.source_row
JOIN qualityops.sensor AS s
  ON s.dataset_version_id = m.dataset_version_id
 AND s.sensor_index = m.sensor_index
WHERE m.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
GROUP BY m.dataset_version_id, m.sensor_index, s.sensor_key, o.outcome
ORDER BY m.sensor_index, o.outcome;
