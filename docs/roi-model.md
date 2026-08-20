# Illustrative ROI model for proposals

This model translates review-time assumptions into a proposal-planning range.
It is not a record of achieved savings. QualityOps has no client-approved labor,
scrap, warranty, license or production savings evidence.

## Formula

```text
gross hours saved = evidence sets x refreshes/year x minutes saved/set / 60
realized annual benefit = gross hours saved x loaded hourly rate x realization factor
year-1 net value = realized benefit - one-time implementation - annual maintenance
year-1 ROI = year-1 net value / (one-time implementation + annual maintenance)
payback months = one-time implementation / (benefit - maintenance) x 12
multi-year ROI = (total realized benefit - total implementation and maintenance cost) / total implementation and maintenance cost
```

The verified technical driver is six reconciled Power BI evidence sets. All
financial and time values below are editable assumptions. The model counts no
license, defect, scrap, downtime, warranty or revenue benefit.

| Assumption | Conservative | Base | Upside |
|---|---:|---:|---:|
| Evidence sets | 6 | 6 | 6 |
| Refreshes per year | 12 | 12 | 12 |
| Minutes saved per set | 20 | 60 | 120 |
| Loaded analyst rate | $45/h | $55/h | $70/h |
| Realization factor | 50% | 70% | 80% |
| One-time implementation | $3,100 | $3,100 | $3,100 |
| Annual maintenance/training | $600 | $600 | $600 |

## Results

| Result | Conservative | Base | Upside |
|---|---:|---:|---:|
| Gross hours released/year | 24 | 72 | 144 |
| Realized annual benefit | $540 | $2,772 | $8,064 |
| Year-1 net value | -$3,160 | -$928 | $4,364 |
| Year-1 ROI | -85.4% | -25.1% | 117.9% |
| Payback | None | 17.1 months | 5.0 months |

At a 10% discount rate, the base case has a three-year NPV of approximately
`$2,301` and nominal three-year ROI of `69.7%`, assuming annual realized benefit
remains `$2,772`. The three-year ROI includes the `$3,100` implementation and
three annual maintenance costs of `$600`. These are planning outputs, not
predictions.

## Use gate

Before a proposal uses any scenario, replace the time, rate, implementation and
maintenance assumptions with client-confirmed inputs. Keep any defect, scrap,
license or revenue benefits at zero until the client supplies auditable evidence.
