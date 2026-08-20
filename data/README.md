# Data policy

Place an authorized `.xlsx` workbook used for local validation in this directory.

Raw spreadsheet and columnar data files are ignored by Git to reduce accidental publication. The original DMAIC/PCBA case is illustrative. Any external, university, partner, or company dataset must be anonymized and explicitly approved before it is committed.

Record only a safe dataset identifier in the public validation template. Do not commit operator names, customer identifiers, confidential specifications, or internal paths.

## Controlled public-data exception

`external/secom/raw/` is an explicit exception for the public UCI SECOM
dataset. Its three original files are versioned only because the source,
license, attribution, acquisition method, file sizes, and SHA-256 acquisition
hashes are documented in `docs/secom-dataset.md`. The files are byte-preserved
through `.gitattributes` and verified before QualityOps parses them.

This exception does not authorize committing other external or local data.
Every future dataset requires its own license, confidentiality, provenance,
integrity, and data-quality review.

## Synthetic SPC validation exception

`spc/qualityops_spc_rbar_n4_v1.csv` is a project-authored, non-confidential
synthetic dataset committed solely for formula validation. Its simulated limits,
target, subgroup definition, method, hashes and Minitab evidence are recorded in
`spc/manifest.json` and `docs/spc-validation.md`. It is not production data and
does not establish customer specifications or real rational subgrouping.
