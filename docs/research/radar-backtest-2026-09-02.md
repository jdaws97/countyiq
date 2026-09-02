# Radar opportunity back-test (2026-09-02)

Deterministic back-test of radar signals against believable subdivision and land-development plans received on the parcel. No model calls.

## Population

| Metric | Value |
|---|---|
| eligible_parcels | 171,510 |
| positives | 496 |
| ambiguous_excluded | 39,809 |
| fit_parcels | 131,701 |
| distinct_patterns | 1,021 |

Label window: plans received in the last 24 months within 30 m of the parcel. Parcels with an older believable plan within 250 m in the last 10 years are excluded from the fit as ambiguous.

## Per-signal evidence

| Signal | Parcels with signal | Positive rate with | Positive rate without | Lift | WoE | Coefficient | Proposed weight | Current weight |
|---|---|---|---|---|---|---|---|---|
| entity_assemblage | 1,086 | 4.604% | 0.341% | 12.22 | +2.55 | +2.597 | +0.23 | +0.00 |
| economic_development_park | 151 | 9.934% | 0.366% | 26.38 | +3.40 | +2.500 | +0.22 | +0.16 |
| assemblage | 8,225 | 1.374% | 0.310% | 3.65 | +1.31 | +1.641 | +0.15 | +0.08 |
| vacancy | 6,180 | 1.343% | 0.329% | 3.57 | +1.29 | +1.353 | +0.12 | +0.12 |
| environmental_diligence | 39,714 | 0.607% | 0.277% | 1.61 | +0.48 | +0.694 | +0.00 | -0.05 |
| zoning_mismatch | 9,710 | 0.639% | 0.356% | 1.70 | +0.54 | +0.643 | +0.06 | +0.10 |
| growth_area | 89,659 | 0.433% | 0.257% | 1.15 | +0.14 | +0.532 | +0.05 | +0.02 |
| tax_distress | 2,413 | 0.746% | 0.370% | 1.98 | +0.71 | +0.394 | +0.04 | +0.10 |
| penndot_project | 13,187 | 0.516% | 0.361% | 1.37 | +0.32 | +0.204 | +0.02 | +0.03 |
| local_traffic_activity | 21,828 | 0.504% | 0.351% | 1.34 | +0.30 | +0.201 | +0.02 | +0.03 |
| municipal_action | 0 | 0.000% | 0.377% | 0.00 | +5.58 | +0.000 | +0.00 | +0.00 |
| zoning_constraint | 6,650 | 0.346% | 0.378% | 0.92 | -0.07 | -0.095 | -0.01 | -0.06 |
| flood_zone | 2,243 | 0.401% | 0.376% | 1.07 | +0.12 | -0.249 | -0.02 | -0.10 |
| soil_constraint | 18,964 | 0.301% | 0.389% | 0.80 | -0.22 | -0.282 | -0.03 | -0.08 |
| ownership_change | 5,115 | 0.411% | 0.375% | 1.09 | +0.11 | -0.535 | +0.00 | +0.10 |
| development_overlay | 963 | 0.000% | 0.379% | 0.00 | -1.99 | -0.734 | +0.00 | +0.04 |

Intercept: -6.742 (ridge λ=2.0).

## Ranking quality

| Scorer | AUC | P@250 | P@1000 | P@5000 |
|---|---|---|---|---|
| current_v5_weights | 0.6228 | 3.200% | 2.652% | 1.620% |
| fitted_logistic | 0.7554 | 8.800% | 5.054% | 3.120% |
| proposed_v6_weights | 0.7255 | 7.629% | 5.400% | 2.714% |

Base positive rate: 0.377%.

## Proposed opportunity score quantiles (raw × 100)

| Quantile | Score |
|---|---|
| top_0.100% | 38 |
| top_0.500% | 30 |
| top_1.000% | 27 |
| top_2.000% | 22 |
| top_5.000% | 18 |
| top_10.000% | 12 |

## Caveats

- Signals are computed on the current snapshot, not the parcel state before the plan was filed.
- ownership_change counts for positives only when the sale predates the plan; other signals have no such guard.
- vacancy is likely under-counted for positives because built-out plans now carry structures, so its coefficient is conservative.
- municipal_action and entity_assemblage depend on Pass 0 extractions and recent-sale data; with few rows their coefficients are dominated by the ridge prior.
- Precision@K is computed with fractional credit inside tied score groups.
- This is predictive evidence for ranking, not a causal or entitlement claim.
