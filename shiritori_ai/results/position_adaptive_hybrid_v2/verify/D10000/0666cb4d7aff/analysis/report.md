# Position-adaptive hybrid analysis

- stage: `verify`
- completed matches/decisions were read from the parent run directory

## Agent summary

| agent | games | wins | win rate | mean time (s) | mean depth | exact success |
|---|---:|---:|---:|---:|---:|---:|
| beam_alpha_beta | 4 | 4 | 1.000 | 0.1774 | 8.94 | 0 |
| dynamic_beam_alpha_beta | 2 | 0 | 0.000 | 0.2446 | 8.73 | 0 |
| dynamic_beam_pvs | 2 | 0 | 0.000 | 0.1803 | 8.77 | 0 |

## Direct matchups

| left | right | W-L-D | left decisive rate | exact binomial p |
|---|---|---:|---:|---:|
| beam_alpha_beta | dynamic_beam_alpha_beta | 2-0-0 | 1.000 | 0.5000 |
| beam_alpha_beta | dynamic_beam_pvs | 2-0-0 | 1.000 | 0.5000 |

Wilson 95% intervals and exact two-sided binomial p-values are descriptive; tuning and final seeds are separated to reduce selection bias.
