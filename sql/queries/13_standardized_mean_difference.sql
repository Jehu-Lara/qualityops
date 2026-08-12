WITH class_statistics AS (
    SELECT
        m.dataset_version_id,
        m.sensor_index,
        s.sensor_key,
        COUNT(m.value) FILTER (WHERE o.outcome = -1) AS pass_count,
        AVG(m.value) FILTER (WHERE o.outcome = -1) AS pass_mean,
        stddev_samp(m.value) FILTER (WHERE o.outcome = -1) AS pass_sample_stddev,
        COUNT(m.value) FILTER (WHERE o.outcome = 1) AS fail_count,
        AVG(m.value) FILTER (WHERE o.outcome = 1) AS fail_mean,
        stddev_samp(m.value) FILTER (WHERE o.outcome = 1) AS fail_sample_stddev
    FROM qualityops.measurement AS m
    JOIN qualityops.observation AS o
      ON o.dataset_version_id = m.dataset_version_id
     AND o.source_row = m.source_row
    JOIN qualityops.sensor AS s
      ON s.dataset_version_id = m.dataset_version_id
     AND s.sensor_index = m.sensor_index
    WHERE m.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
    GROUP BY m.dataset_version_id, m.sensor_index, s.sensor_key
), variances AS (
    SELECT
        cs.*,
        cs.pass_sample_stddev * cs.pass_sample_stddev AS pass_sample_variance,
        cs.fail_sample_stddev * cs.fail_sample_stddev AS fail_sample_variance
    FROM class_statistics AS cs
), pooled AS (
    SELECT
        v.*,
        CASE
            WHEN v.pass_count < 2 OR v.fail_count < 2
              OR v.pass_sample_variance IS NULL OR v.fail_sample_variance IS NULL
              OR v.pass_count + v.fail_count - 2 <= 0
            THEN NULL
            ELSE (
                (v.fail_count - 1) * v.fail_sample_variance
                + (v.pass_count - 1) * v.pass_sample_variance
            ) / (v.fail_count + v.pass_count - 2)
        END AS pooled_variance
    FROM variances AS v
), results AS (
    SELECT
        p.*,
        CASE
            WHEN p.pooled_variance IS NULL OR p.pooled_variance <= 0
            THEN NULL
            ELSE (p.fail_mean - p.pass_mean) / sqrt(p.pooled_variance)
        END AS standardized_mean_difference
    FROM pooled AS p
)
SELECT
    r.dataset_version_id,
    r.sensor_index,
    r.sensor_key,
    r.pass_count,
    r.pass_mean,
    r.pass_sample_variance,
    r.fail_count,
    r.fail_mean,
    r.fail_sample_variance,
    r.pooled_variance,
    r.standardized_mean_difference
FROM results AS r
ORDER BY abs(r.standardized_mean_difference) DESC NULLS LAST, r.sensor_index;
