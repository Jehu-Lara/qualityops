# Portfolio claim boundaries

This record keeps public statements aligned with available evidence.

## Supported statements

- Built an installable Python package and CLI for auditable manufacturing-data analysis.
- Implemented tested overall process-performance metrics (`Pp/Ppk`).
- Implemented `Cp/Cpk` formulas using an explicitly supplied within-subgroup sigma.
- Implemented equal-size Xbar-R charts, Test 1 and `Rbar/d2` within-sigma
  estimation; the n=4 path reproduces unrounded Minitab 22.5.1 reference
  results within `1e-9` on a hash-locked synthetic dataset.
- Added strict Excel ingestion, data-quality checks, automated tests, and a Minitab comparison protocol.
- Implemented and independently validated one-way ANOVA, Pearson correlation,
  and simple linear regression against Minitab.
- Incorporated the public UCI SECOM manufacturing dataset with documented
  provenance, CC BY 4.0 attribution, verified acquisition hashes, and a
  reproducible deterministic data-quality audit.
- Implemented a reproducible, transactional, and idempotent PostgreSQL load of
  the public SECOM dataset with twenty auditable SQL queries.
- Built a reproducible one-page Power BI view backed by PostgreSQL to communicate
  data quality, observed outcomes, and descriptive associations in the public
  SECOM dataset, with reconciliation and auditable evidence.
- Developed the repository from an illustrative DMAIC/PCBA case study prepared for Green Belt Level II evaluation.

## Statements not currently supported

- “CSSC-certified Green Belt Level II” until formal approval is received.
- “Deployed in a production plant” or “used by a manufacturing client.”
- “Delivered verified savings” or any financial result not approved by the relevant owner and finance function.
- “Replaced Minitab,” “matches every Minitab method,” or “automatically validates
  process capability.”
- “AI-powered industrial platform”; the current release is deterministic analytics, not an AI system.
- “SECOM demonstrates process capability”; the dataset does not provide
  documented specification limits or a within-subgroup sigma suitable for
  `Cp/Cpk/Pp/Ppk` conclusions.
- “SECOM identifies causes of manufacturing failures”; association or data
  quality evidence does not establish causality.
- “SECOM proves production readiness”; a public dataset audit is not a
  production deployment, MES/QMS integration, or operational validation.
- “The PostgreSQL loader demonstrates production capacity or industrial
  scalability”; local reproducibility is not production evidence.
- “Power BI is part of the persistence layer”; the PBIP project is an
  independent read-only consumer of PostgreSQL.
- “Delivered ROI or savings.” The public ROI model contains assumptions for
  proposals, not observed client or production results.
- “Phase II process monitoring.” The current SPC path does not apply frozen
  historical control limits to separate new observations.
- “The milestone includes FastAPI, machine learning, or AI”; those capabilities
  remain outside this milestone.

## Governance through Gate B

Gate A and Gate B are complete for the bounded Power BI statement above. PR #19
was merged via Rebase and merge, producing main SHA
e85c0c57907a44ea6c7d63b5ed333da4a432ef51. All four checks on main completed
with SUCCESS. No release or tag was created; CHANGELOG.md remains under
Unreleased. There was no publication to Power BI Service or Fabric and no
gateway was configured. This status does not authorize claims about production,
causality, capability, prediction, AI, or industrial scale.

## Promotion rule

Move a statement into the supported section only when there is durable evidence such as an approval, reproducible validation record, authorized real dataset, deployment log, or client confirmation.
