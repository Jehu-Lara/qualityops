SELECT
    o.dataset_version_id,
    o.source_row,
    o.observed_at,
    o.outcome,
    CASE o.outcome WHEN -1 THEN 'pass' WHEN 1 THEN 'fail' END AS outcome_name
FROM qualityops.observation AS o
JOIN qualityops.measurement AS m
  ON m.dataset_version_id = o.dataset_version_id
 AND m.source_row = o.source_row
WHERE o.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
GROUP BY o.dataset_version_id, o.source_row, o.observed_at, o.outcome
HAVING COUNT(*) = 590
   AND COUNT(m.value) = 590
ORDER BY o.source_row;
