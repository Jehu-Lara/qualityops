SELECT
    o.dataset_version_id,
    CAST(o.observed_at AS DATE) AS observed_date,
    COUNT(*) AS observation_count,
    COUNT(*) FILTER (WHERE o.outcome = -1) AS pass_count,
    COUNT(*) FILTER (WHERE o.outcome = 1) AS fail_count,
    COUNT(*) FILTER (WHERE o.outcome = 1)::DOUBLE PRECISION / COUNT(*) AS fail_rate
FROM qualityops.observation AS o
WHERE o.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
GROUP BY o.dataset_version_id, CAST(o.observed_at AS DATE)
ORDER BY observed_date;
