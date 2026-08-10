# Validation record

## Controlled inputs

- Dataset identifier: `dataset_validacion.xlsx` (Mock dataset)
- File SHA-256: `c1056405e908bfe6d46734a0851c8b5cef9b0e2d9a61388a530dda9dadff7abb`
- Validation date: `2026-08-10`
- Python version: `3.11`
- QualityOps version/commit: `826686b`
- Minitab version: `Minitab 21`
- Worksheet and column: `Sheet 0 / Medicion_mL`
- Observations included: `50`
- Missing/excluded observations: `0`
- LSL / USL / units: `495.0 / 505.0 / mL`
- Subgroup definition: `Not applicable (overall capability test)`

## Reproducibility Evidence

### Minitab Configuration
- **Tool:** Stat > Quality Tools > Capability Analysis (Normal)
- **Data column:** `Medicion_mL`
- **Subgroup size:** `1`
- **Lower spec:** `495`
- **Upper spec:** `505`
- **Exported precise targets:** Mean = `500.6368000000`, Overall Std Dev = `1.5236334660`, Pp = `1.0938763842`, Ppk = `0.9545602879`.

**Visual Evidence:**
![Minitab Capability Analysis Results](./assets/Process%20Capability%20Report%20for%20Medicion_mL.png)

#### QualityOps Execution

**Command:**

```bash
qualityops analyze --file data\dataset_validation.xlsx --column Medicion_mL --lsl 495 --usl 505
```

**Output:**

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