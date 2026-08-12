WITH selected_sensors AS (
    SELECT
        sx.dataset_version_id,
        sx.sensor_index AS sensor_index_x,
        sx.sensor_key AS sensor_key_x,
        sy.sensor_index AS sensor_index_y,
        sy.sensor_key AS sensor_key_y
    FROM qualityops.sensor AS sx
    JOIN qualityops.sensor AS sy
      ON sy.dataset_version_id = sx.dataset_version_id
    WHERE sx.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
      AND sx.sensor_key = CAST(:sensor_key_x AS TEXT)
      AND sy.sensor_key = CAST(:sensor_key_y AS TEXT)
), pairs AS (
    SELECT
        ss.dataset_version_id,
        ss.sensor_key_x,
        ss.sensor_key_y,
        mx.value AS value_x,
        my.value AS value_y
    FROM selected_sensors AS ss
    JOIN qualityops.measurement AS mx
      ON mx.dataset_version_id = ss.dataset_version_id
     AND mx.sensor_index = ss.sensor_index_x
    JOIN qualityops.measurement AS my
      ON my.dataset_version_id = mx.dataset_version_id
     AND my.source_row = mx.source_row
     AND my.sensor_index = ss.sensor_index_y
)
SELECT
    p.dataset_version_id,
    p.sensor_key_x,
    p.sensor_key_y,
    COUNT(*) FILTER (WHERE p.value_x IS NOT NULL AND p.value_y IS NOT NULL) AS paired_count,
    corr(p.value_x, p.value_y) AS correlation
FROM pairs AS p
GROUP BY p.dataset_version_id, p.sensor_key_x, p.sensor_key_y
ORDER BY p.dataset_version_id;
