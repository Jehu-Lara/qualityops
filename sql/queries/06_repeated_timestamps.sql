SELECT
    o.dataset_version_id,
    o.observed_at,
    COUNT(*) AS occurrence_count,
    array_agg(o.source_row ORDER BY o.source_row) AS source_rows,
    array_agg(o.outcome ORDER BY o.source_row) AS outcomes
FROM qualityops.observation AS o
WHERE o.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
GROUP BY o.dataset_version_id, o.observed_at
HAVING COUNT(*) > 1
ORDER BY o.observed_at;
