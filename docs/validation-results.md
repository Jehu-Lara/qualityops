# Validation record

## Controlled inputs

- Dataset identifier: `dataset_validacion.xlsx`
- Validation date: `2026-08-10`
- Python version: `3.11`
- QualityOps version/commit: `826686b`
- Minitab version: `Minitab 21`
- Worksheet and column: `Sheet 0 / Medicion_mL`
- Observations included: `50`
- Missing/excluded observations: `0`
- LSL / USL / units: `495.0 / 505.0 / mL`
- Subgroup definition: `Not applicable (overall capability test)`

## Overall performance

| Metric | Python | Minitab | Absolute difference | Pass (`<= 1e-9`) |
|---|---:|---:|---:|:---:|
| Mean | 500.6368000000 | 500.6368000000 | 0.0000000000 | PASS |
| Overall sample standard deviation | 1.5236334660 | 1.5236334660 | 0.0000000000 | PASS |
| Pp | 1.0938763842 | 1.0938763842 | 4.44e-16 | PASS |
| Ppk | 0.9545602879 | 0.9545602879 | 0.0000000000 | PASS |

## Potential capability

- Minitab within-sigma estimator: `Not evaluated in this run`
- Unrounded within sigma supplied to Python: `None (--within-sigma not provided)`

| Metric | Python | Minitab | Absolute difference | Pass (`<= 1e-9`) |
|---|---:|---:|---:|:---:|
| Cp | N/A | 1.20 | N/A | N/A |
| Cpk | N/A | 1.05 | N/A | N/A |

## Review notes
- The Python implementation correctly calculates overall sample variation using N-1 degrees of freedom.
- The JSON output explicitly returned `"potential": null`, proving that the tool strictly respects the statistical contract defined in the README (it does not invent a within-subgroup sigma).
- Pp and Ppk match Minitab's overall capability calculation exactly. The minor 4.44e-16 variance is a standard floating-point remainder, well within the 1e-9 tolerance.
