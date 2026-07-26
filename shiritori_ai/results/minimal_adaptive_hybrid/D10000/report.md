# Minimal D10000 adaptive-hybrid experiment

## Data

- Saved positions: 50
- Exact-complete positions: 0
- Mixed win/loss exact positions: 0
- Stable deep-reference positions: 49

## Fixed-position screening

| profile | match rate | time (s) | nodes | depth | timeout | exact nontrivial | changes | improve | regress | accepted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| fixed_beam_alpha_beta | 69.4% | 0.1214 | 1670 | 8.00 | 6.0% | 0 | 0 | 0 | 0 | no |
| gap_conservative | 44.9% | 0.0804 | 1102 | 8.00 | 0.0% | 0 | 25 | 4 | 16 | no |
| gap_responsive | 55.1% | 0.0122 | 182 | 8.00 | 0.0% | 0 | 26 | 6 | 13 | no |
| proof_strict | 69.4% | 0.1196 | 1639 | 8.00 | 4.0% | 0 | 0 | 0 | 0 | no |
| proof_moderate | 69.4% | 0.1200 | 1628 | 8.00 | 8.0% | 0 | 0 | 0 | 0 | no |

## Selection

- Accepted profiles: none
- Dynamic Beam acceptance: accuracy not degraded and time or nodes reduced by at least 10%.
- Selective proof acceptance: nontrivial proofs, at least two choice changes, improvements exceed regressions, and time stays within 125% of baseline.

## Short matches

- No method passed screening, so matches were skipped.

## Reproduction

```bash
.venv/bin/python -u src/run_minimal_adaptive_hybrid_experiment.py \
  --stage all --truth-time-sec 0.3 --confirm-d10000 \
  --output results/minimal_adaptive_hybrid/D10000_rerun
```

The combined DynamicSelectiveProof agent was intentionally not implemented unless both mechanisms passed the independent screen.
