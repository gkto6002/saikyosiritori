# Position-adaptive hybrid analysis

- stage: `tune`
- completed matches/decisions were read from the parent run directory

## Agent summary

| agent | games | wins | win rate | mean time (s) | mean depth | exact success |
|---|---:|---:|---:|---:|---:|---:|
| beam_alpha_beta | 180 | 120 | 0.667 | 0.2473 | 8.52 | 0 |
| branch_switch_alpha_beta | 30 | 8 | 0.267 | 0.3501 | 7.65 | 0 |
| dynamic_beam_alpha_beta | 30 | 12 | 0.400 | 0.4194 | 5.35 | 0 |
| dynamic_beam_pvs | 30 | 12 | 0.400 | 0.4099 | 5.37 | 0 |
| endgame_exact_hybrid | 30 | 16 | 0.533 | 0.2655 | 8.31 | 14 |
| integrated_adaptive_hybrid | 30 | 5 | 0.167 | 0.4222 | 4.86 | 25 |
| research_adaptive_beam | 30 | 7 | 0.233 | 0.4150 | 5.03 | 0 |

## Direct matchups

| left | right | W-L-D | left decisive rate | exact binomial p |
|---|---|---:|---:|---:|
| beam_alpha_beta | branch_switch_alpha_beta | 22-8-0 | 0.733 | 0.0161 |
| beam_alpha_beta | dynamic_beam_alpha_beta | 18-12-0 | 0.600 | 0.3616 |
| beam_alpha_beta | dynamic_beam_pvs | 18-12-0 | 0.600 | 0.3616 |
| beam_alpha_beta | endgame_exact_hybrid | 14-16-0 | 0.467 | 0.8555 |
| beam_alpha_beta | integrated_adaptive_hybrid | 25-5-0 | 0.833 | 0.0003 |
| beam_alpha_beta | research_adaptive_beam | 23-7-0 | 0.767 | 0.0052 |

Wilson 95% intervals and exact two-sided binomial p-values are descriptive; tuning and final seeds are separated to reduce selection bias.
