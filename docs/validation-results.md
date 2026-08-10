# Python–Minitab validation record

## Validation scope

This record validates QualityOps overall process-performance calculations against Minitab using the same simulated, non-confidential dataset, observations, specification limits, and overall sample standard deviation.

The comparison covers:

- Arithmetic mean
- Overall sample standard deviation
- `Pp`
- `Ppk`

`Cp` and `Cpk` are outside the scope of this validation because no independently documented within-subgroup standard deviation was supplied to QualityOps.

## Controlled inputs

| Parameter | Value |
|---|---|
| Dataset identifier | `dataset_validation.xlsx` |
| Dataset type | Simulated and non-confidential |
| Dataset SHA-256 | `c1056405e908bfe6d46734a0851c8b5cef9b0e2d9a61388a530dda9dadff7abb` |
| Validation date | `2026-08-10` |
| Python version | `3.11` |
| QualityOps version/commit | `826686b` |
| Minitab version | `Minitab 21` |
| Worksheet | First worksheet (`Sheet 0`) |
| Measurement column | `Medicion_mL` |
| Measurement unit | `mL` |
| Source observations | `50` |
| Observations analyzed | `50` |
| Missing observations excluded | `0` |
| Lower specification limit (LSL) | `495 mL` |
| Upper specification limit (USL) | `505 mL` |
| QualityOps standard-deviation estimator | Overall sample standard deviation (`n - 1`) |
| Comparison tolerance | Absolute difference ≤ `1e-9` |

## Minitab configuration

The Minitab analysis was configured as follows:

- **Menu:** `Stat > Quality Tools > Capability Analysis > Normal`
- **Data column:** `Medicion_mL`
- **Subgroup size:** `1`
- **Lower specification limit:** `495`
- **Upper specification limit:** `505`
- **Comparison scope:** Overall statistics only

The Minitab values used in the comparison were transcribed at the displayed precision:

- Mean: `500.6368000000`
- Overall standard deviation: `1.5236334660`
- Pp: `1.0938763842`
- Ppk: `0.9545602879`

## Python–Minitab comparison

| Metric | QualityOps | Minitab | Absolute difference | Acceptance criterion | Result |
|---|---:|---:|---:|---:|:---:|
| Mean | 500.6368000000 | 500.6368000000 | 0.0000e+00 | ≤ 1e-9 | PASS |
| Overall sample standard deviation | 1.5236334660198 | 1.5236334660 | 1.9800e-11 | ≤ 1e-9 | PASS |
| Pp | 1.0938763842070975 | 1.0938763842 | 7.0975e-12 | ≤ 1e-9 | PASS |
| Ppk | 0.954560287914483 | 0.9545602879 | 1.4483e-11 | ≤ 1e-9 | PASS |

All four evaluated metrics satisfy the predefined acceptance criterion.

The small absolute differences result from the displayed precision of the Minitab values and normal floating-point representation. They are not statistical variances and do not indicate a meaningful disagreement between the two implementations.

## QualityOps execution

The following command was used from the repository root:

```bash
qualityops analyze --file data/dataset_validation.xlsx --column Medicion_mL --lsl 495 --usl 505
```

The `--within-sigma` option was intentionally omitted. Therefore, QualityOps correctly returned `"potential": null` and did not calculate `Cp` or `Cpk`.

## QualityOps JSON output

```json
{
  "source": {
    "kind": "excel",
    "path": "data\\dataset_validation.xlsx",
    "column": "Medicion_mL",
    "source_row_count": 50,
    "missing_measurements_excluded": 0
  },
  "analysis": {
    "overall": {
      "count": 50,
      "mean": 500.6368,
      "overall_sample_std": 1.5236334660198,
      "pp": 1.0938763842070975,
      "ppl": 1.233192480499712,
      "ppu": 0.954560287914483,
      "ppk": 0.954560287914483,
      "lsl": 495.0,
      "usl": 505.0
    },
    "potential": null
  }
}
```

## Visual evidence

The corresponding Minitab output is preserved in the repository:

![Minitab Capability Analysis Results](./assets/Process%20Capability%20Report%20for%20Medicion_mL.png)

## Integrity and confidentiality

- The dataset was generated specifically for validation.
- It contains no real Green Belt project information.
- It contains no confidential company, customer, employee, or production data.
- The SHA-256 digest records the exact dataset version used during the comparison.
- Raw confidential industrial data were not used or published.

## Validation conclusion

QualityOps reproduced Minitab’s mean, overall sample standard deviation, `Pp`, and `Ppk` within the predefined absolute tolerance of `1e-9`.

Therefore, the overall process-performance calculations evaluated in this exercise are considered successfully validated against the displayed Minitab results for this controlled dataset.

This result validates only the calculations and conditions documented in this record. It does not establish process stability, normality, measurement-system adequacy, causal improvement, certified financial impact, production readiness, or certification approval.