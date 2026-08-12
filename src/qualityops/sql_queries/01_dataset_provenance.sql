SELECT
    dv.dataset_version_id,
    d.dataset_code,
    d.name,
    d.publisher,
    d.doi,
    d.source_url,
    d.license_spdx,
    dv.version_label,
    dv.acquired_on,
    dv.loaded_at,
    dv.audit_schema_version,
    dv.content_fingerprint
FROM qualityops.dataset_version AS dv
JOIN qualityops.dataset AS d
  ON d.dataset_id = dv.dataset_id
WHERE dv.dataset_version_id = CAST(:dataset_version_id AS BIGINT)
ORDER BY dv.dataset_version_id;
