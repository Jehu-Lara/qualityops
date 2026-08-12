# Audited PostgreSQL queries

These twenty MIT-licensed files are read-only `SELECT` statements for one
explicit `dataset_version_id`. They use schema-qualified objects, explicit
columns, SQLAlchemy `:name` parameters wrapped in `CAST`, and deterministic
ordering. DDL, DML, `COPY`, `ON CONFLICT` and environment-derived values are
forbidden.

Rates named `fail_rate` or `missing_rate` use `0–1`; percentages use `0–100`.
`source_row` is one-based and `sensor_index` is zero-based.

| File | Parameters and types | Output columns, semantics and order |
|---|---|---|
| `01_dataset_provenance.sql` | `dataset_version_id BIGINT` | `dataset_version_id`, `dataset_code`, `name`, `publisher`, `doi`, `source_url`, `license_spdx`, `version_label`, `acquired_on`, `loaded_at`, `audit_schema_version`, `content_fingerprint`; one row when found, otherwise zero; order by version ID. |
| `02_source_file_integrity.sql` | `dataset_version_id BIGINT` | `dataset_version_id`, `filename`, `role`, `byte_size`, `sha256`; order by `filename`. |
| `03_load_reconciliation.sql` | `dataset_version_id BIGINT` | `dataset_version_id`, expected/actual observation counts and `observations_match`, expected/actual sensor counts and `sensors_match`, expected/actual measurement counts and `measurements_match`, expected/actual missing counts and `missing_measurements_match`, `measurements_per_observation_match`; one row when found. |
| `04_outcome_distribution.sql` | `dataset_version_id BIGINT` | Version, `outcome`, `outcome_name`, `observation_count`, `observation_percentage` (`0–100`); order by `outcome`. |
| `05_daily_yield.sql` | `dataset_version_id BIGINT` | Version, `observed_date`, total/pass/fail counts, `fail_rate` (`0–1`); order by date. |
| `06_repeated_timestamps.sql` | `dataset_version_id BIGINT` | Version, `observed_at`, `occurrence_count`, `source_rows`, `outcomes`; only counts above one. Both arrays use `array_agg(... ORDER BY source_row)` and remain aligned; order by timestamp. |
| `07_sensor_missingness.sql` | `dataset_version_id BIGINT` | Version, sensor index/key, measurement/nonmissing/missing counts, `missing_rate` (`0–1`); order by sensor index. |
| `08_observation_missingness.sql` | `dataset_version_id BIGINT` | Version, source row, timestamp, outcome/name, sensor/nonmissing/missing counts and `missing_rate` (`0–1`); order by source row. |
| `09_sensor_missingness_by_outcome.sql` | `dataset_version_id BIGINT` | Version, sensor index/key, outcome/name, observation/nonmissing/missing counts and `missing_rate` (`0–1`); order by sensor index, outcome. |
| `10_constant_sensors.sql` | `dataset_version_id BIGINT` | Version, sensor index/key, nonmissing/distinct counts and `constant_value`; requires `COUNT(value)>0` and exactly one distinct non-NULL value; order by sensor index. |
| `11_sensor_descriptive_statistics.sql` | `dataset_version_id BIGINT` | Version, sensor index/key, measurement/nonmissing/missing counts, min, max, mean and `sample_stddev=stddev_samp(value)`; order by sensor index. |
| `12_pass_fail_mean_comparison.sql` | `dataset_version_id BIGINT` | Version, sensor index/key, pass count/mean, fail count/mean and `fail_minus_pass_mean=fail_mean-pass_mean`; order by sensor index. |
| `13_standardized_mean_difference.sql` | `dataset_version_id BIGINT` | Version, sensor index/key; class counts, means and sample variances; `pooled_variance`; standardized fail-minus-pass difference. Order by absolute standardized difference descending `NULLS LAST`, then sensor index. |
| `14_sensor_time_series.sql` | `dataset_version_id BIGINT`, `sensor_key TEXT`, `start_at TIMESTAMP WITHOUT TIME ZONE`, `end_at TIMESTAMP WITHOUT TIME ZONE` | Version, sensor index/key, source row, timestamp, outcome/name, value and missing flag for `[start_at,end_at)`; order by timestamp, source row. |
| `15_daily_sensor_summary.sql` | `dataset_version_id BIGINT`, `sensor_key TEXT` | Version, sensor index/key, date, measurement/nonmissing/missing counts, min, max, mean and sample standard deviation; order by date. |
| `16_observation_profile.sql` | `dataset_version_id BIGINT`, `source_row INTEGER` | Version, source row, timestamp, outcome/name, sensor index/key, value and missing flag; order by sensor index. |
| `17_complete_observations.sql` | `dataset_version_id BIGINT` | Version, source row, timestamp, outcome/name only for observations having exactly 590 rows and 590 non-NULL values; order by source row. |
| `18_extreme_measurement_diagnostics.sql` | `dataset_version_id BIGINT`, `z_threshold DOUBLE PRECISION` | Version, sensor index/key, `row_kind`, `reason`, sample count/stddev, source row, timestamp, outcome, value, z-score and threshold. Calculable sensors return only absolute z-scores at or above the threshold; each noncalculable sensor returns exactly one diagnostic row. Order by sensor index, row kind, source row `NULLS FIRST`. |
| `19_sensor_pair_correlation.sql` | `dataset_version_id BIGINT`, `sensor_key_x TEXT`, `sensor_key_y TEXT` | Version, both keys, paired count and Pearson correlation. Zero rows if either sensor/version is absent; one NULL correlation for insufficient pairs or nonpositive variance. |
| `20_measurement_long_fact.sql` | `dataset_version_id BIGINT` | Version, source row, timestamp, outcome/name, sensor index/key, value and missing flag; order by source row, sensor index. SECOM yields 924,530 rows and must be consumed with streaming and `fetchmany(10_000)`, never `fetchall()`. |

## Statistical definitions and NULL cases

For query 13:

```text
pass_sample_variance = stddev_samp(pass_value)²
fail_sample_variance = stddev_samp(fail_value)²
pooled_variance =
  ((n_fail - 1) * fail_sample_variance
   + (n_pass - 1) * pass_sample_variance)
  / (n_fail + n_pass - 2)
standardized_mean_difference =
  (fail_mean - pass_mean) / sqrt(pooled_variance)
```

`var_samp` is equivalent; `var_pop` is prohibited. Query 18 uses
`sample_stddev=stddev_samp(value)` and
`z_score=(value-mean_value)/sample_stddev`. `insufficient_sample` means fewer
than two nonmissing values. `nonpositive_variance` means at least two values
but sample deviation is NULL, zero or negative. Extreme rows have `reason=NULL`;
unscorable rows have NULL observation/value/z-score fields.

Sample deviation is NULL below two values. Means are NULL with no values;
mean differences are NULL if either mean is absent. Pooled statistics are NULL
for insufficient samples, missing class variance, nonpositive degrees of
freedom or nonpositive pooled variance. Correlation is NULL below two complete
pairs or with nonpositive variance in either sensor.
