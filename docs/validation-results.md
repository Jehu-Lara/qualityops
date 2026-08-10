## Python–Minitab Comparison

The validation used the simulated, non-confidential dataset `dataset_validation.xlsx`, containing 50 observations and no missing values.

### Analysis configuration

| Parameter | Value |
|---|---:|
| Measurement unit | mm |
| Lower specification limit (LSL) | 495 |
| Upper specification limit (USL) | 505 |
| Observations | 50 |
| Standard deviation method | Overall standard deviation |
| Comparison tolerance | ≤ 1e-9 |

Because this validation uses the overall standard deviation, the appropriate capability indices are `Pp` and `Ppk`. `Cp` and `Cpk` were not evaluated because a documented within-subgroup standard deviation was not available.

### Results

| Metric | Python | Minitab | Absolute difference | Result |
|---|---:|---:|---:|:---:|
| Mean | 500.6368000000 | 500.6368000000 | 0.00e+00 | PASS |
| Overall standard deviation | 1.5236334660198 | 1.5236334660 | 1.98e-11 | PASS |
| Pp | 1.0938763842070975 | 1.0938763842 | 7.10e-12 | PASS |
| Ppk | 0.954560287914483 | 0.9545602879 | 4.48e-12 | PASS |
| Cp | N/A | N/A | N/A | NOT EVALUATED |
| Cpk | N/A | N/A | N/A | NOT EVALUATED |

All evaluated metrics satisfy the predefined acceptance criterion of an absolute difference less than or equal to `1e-9`.

The observed differences are attributable to numerical rounding and floating-point representation. They are not statistical variances and do not indicate a meaningful disagreement between Python and Minitab.

### QualityOps execution

```bash
qualityops capability dataset_validation.xlsx \
  --column Measurement \
  --lsl 495 \
  --usl 505 \
  --json
```

### QualityOps JSON output

```json
{
  "count": 50,
  "mean": 500.6368,
  "overall_standard_deviation": 1.5236334660198,
  "lsl": 495.0,
  "usl": 505.0,
  "pp": 1.0938763842070975,
  "ppk": 0.954560287914483,
  "cp": null,
  "cpk": null
}
```

### Reproducibility evidence

- Dataset: `dataset_validation.xlsx`
- Dataset type: simulated and non-confidential
- Dataset SHA-256: `[PASTE_THE_ACTUAL_SHA256_HASH_HERE]`
- Minitab method: Normal Capability Analysis using the overall standard deviation
- Specification limits: LSL = 495 mm; USL = 505 mm
- QualityOps output: included above
- Minitab output: included in the repository as supporting evidence
- Acceptance criterion: absolute difference ≤ `1e-9`

### Conclusion

The Python implementation reproduces Minitab’s mean, overall standard deviation, `Pp`, and `Ppk` results within the predefined numerical tolerance. Therefore, the overall process-capability calculations evaluated in this exercise are considered successfully validated against Minitab.

This validation is based exclusively on simulated data. It does not represent a completed industrial implementation, certified financial impact, or evidence of certification approval.