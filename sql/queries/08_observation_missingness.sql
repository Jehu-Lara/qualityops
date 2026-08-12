SELECT
    m.dataset_version_id,
    m.source_row,
    o.observed_at,
    o.outcome,
    CASE o.outcome WHEN -1 THEN 'pass' WHEN 1 THEN 'fail' END AS outcome_name,
    COUNT(*) AS sensor_count,
    COUNT(m.value) AS nonmissing_count,
    COUNT(*) FILTER (WHERE m.value IS NULL) AS missing_count,
    COUNT(*) FILTER (WHERE m.value IS NULL)::DOUBLE PRECISION / COUNT(*) AS missing_rate
FROM qualityops.measurement AS m
JOIN qualityops.observation AS o
  ON o.dataset_version_id = m.dataset_version_id
 AND o.source_row = m.source_row
WHERE m.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
GROUP BY m.dataset_version_id, m.source_row, o.observed_at, o.outcome
ORDER BY m.source_row;
