SELECT
    sf.dataset_version_id,
    sf.filename,
    sf.role,
    sf.byte_size,
    sf.sha256
FROM qualityops.source_file AS sf
WHERE sf.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
ORDER BY sf.filename;
