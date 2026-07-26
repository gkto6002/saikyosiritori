# Position-adaptive hybrid analysis

- stage: `tune`
- completed matches/decisions were read from the parent run directory

## Agent summary

| agent | games | wins | win rate | mean time (s) | mean depth | exact success |
|---|---:|---:|---:|---:|---:|---:|
| alpha_beta | 10 | 3 | 0.300 | 0.3380 | 6.29 | 0 |
| beam_alpha_beta | 140 | 88 | 0.629 | 0.2218 | 8.91 | 0 |
| beam_pvs | 10 | 3 | 0.300 | 0.2261 | 8.92 | 0 |
| dynamic_beam_alpha_beta | 20 | 5 | 0.250 | 0.2788 | 8.42 | 0 |
| dynamic_beam_pvs | 20 | 6 | 0.300 | 0.2566 | 8.50 | 0 |
| dynamic_proof_extension_beam_alpha_beta | 20 | 9 | 0.450 | 0.3160 | 7.59 | 0 |
| endgame_exact_hybrid | 20 | 11 | 0.550 | 0.2374 | 8.92 | 9 |
| proof_extension_beam_alpha_beta | 20 | 8 | 0.400 | 0.3208 | 8.28 | 50686 |
| research_adaptive_beam | 20 | 7 | 0.350 | 0.3488 | 8.04 | 0 |

## Direct matchups

| left | right | W-L-D | left decisive rate | exact binomial p |
|---|---|---:|---:|---:|
| alpha_beta | beam_alpha_beta | 3-7-0 | 0.300 | 0.3438 |
| beam_alpha_beta | beam_pvs | 7-3-0 | 0.700 | 0.3438 |
| beam_alpha_beta | dynamic_beam_alpha_beta | 15-5-0 | 0.750 | 0.0414 |
| beam_alpha_beta | dynamic_beam_pvs | 14-6-0 | 0.700 | 0.1153 |
| beam_alpha_beta | dynamic_proof_extension_beam_alpha_beta | 11-9-0 | 0.550 | 0.8238 |
| beam_alpha_beta | endgame_exact_hybrid | 9-11-0 | 0.450 | 0.8238 |
| beam_alpha_beta | proof_extension_beam_alpha_beta | 12-8-0 | 0.600 | 0.5034 |
| beam_alpha_beta | research_adaptive_beam | 13-7-0 | 0.650 | 0.2632 |

Wilson 95% intervals and exact two-sided binomial p-values are descriptive; tuning and final seeds are separated to reduce selection bias.
