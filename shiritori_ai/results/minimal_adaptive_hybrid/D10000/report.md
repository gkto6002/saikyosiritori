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

- gap_conservative: 3-7-0 (30.0%), internal timeouts 6, match timeouts 0, invalid moves 0
- gap_responsive: 3-7-0 (30.0%), internal timeouts 8, match timeouts 0, invalid moves 0
- proof_moderate: 7-3-0 (70.0%), internal timeouts 17, match timeouts 0, invalid moves 0
- proof_strict: 7-3-0 (70.0%), internal timeouts 16, match timeouts 0, invalid moves 0

## Explicit five-agent round robin

- fixed_beam_alpha_beta: 20-20-0 (50.0%), n=40, first 20, second 20
- gap_conservative: 19-21-0 (47.5%), n=40, first 20, second 20
- gap_responsive: 10-30-0 (25.0%), n=40, first 20, second 20
- proof_moderate: 28-12-0 (70.0%), n=40, first 20, second 20
- proof_strict: 23-17-0 (57.5%), n=40, first 20, second 20

## Reproduction

```bash
.venv/bin/python -u src/run_minimal_adaptive_hybrid_experiment.py \
  --stage all --truth-time-sec 0.3 --confirm-d10000 \
  --output results/minimal_adaptive_hybrid/D10000_rerun
```

The combined DynamicSelectiveProof agent was intentionally not implemented unless both mechanisms passed the independent screen.
