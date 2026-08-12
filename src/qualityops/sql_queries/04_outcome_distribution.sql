SELECT
    o.dataset_version_id,
    o.outcome,
    CASE o.outcome WHEN -1 THEN 'pass' WHEN 1 THEN 'fail' END AS outcome_name,
    COUNT(*) AS observation_count,
    100.0 * COUNT(*) / SUM(COUNT(*)) OVER () AS observation_percentage
FROM qualityops.observation AS o
WHERE o.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
GROUP BY o.dataset_version_id, o.outcome
ORDER BY o.outcome;
