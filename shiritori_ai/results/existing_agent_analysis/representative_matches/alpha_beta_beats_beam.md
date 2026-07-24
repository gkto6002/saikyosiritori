# alpha_beta_beats_beam: D1000_seed0_beam_negamax_vs_alpha_beta

- D=1000 seed=0
- beam_negamax vs alpha_beta
- winner=alpha_beta turns=26

## 全手順

| 手 | AI | 必要文字 | 辺 | risk | 候補 | 深度 | nodes | score |
|---:|---|---|---|---|---:|---:|---:|---:|
| 1 | beam_negamax | ANY | る→る | normal | 640 | 5 | 234 | 533.144 |
| 2 | alpha_beta | る | る→む | near_death | 1 | 5 | 235 | 150.0 |
| 3 | beam_negamax | む | む→や | caution | 9 | 5 | 1009 | 237.26 |
| 4 | alpha_beta | や | や→ざ | caution | 6 | 5 | 402 | 237.26 |
| 5 | beam_negamax | ざ | ざ→か | danger | 4 | 5 | 382 | 150.0 |
| 6 | alpha_beta | か | か→や | normal | 20 | 5 | 411 | 121.398 |
| 7 | beam_negamax | や | や→む | danger | 5 | 5 | 638 | 205.796 |
| 8 | alpha_beta | む | む→わ | caution | 8 | 5 | 311 | 121.07375 |
| 9 | beam_negamax | わ | わ→ば | caution | 7 | 5 | 740 | 237.45636363636362 |
| 10 | alpha_beta | ば | ば→ぐ | caution | 6 | 5 | 130 | 121.07375 |
| 11 | beam_negamax | ぐ | ぐ→か | danger | 4 | 5 | 501 | 150.0 |
| 12 | alpha_beta | か | か→や | normal | 20 | 5 | 271 | 121.398 |
| 13 | beam_negamax | や | や→か | danger | 4 | 5 | 451 | 121.07375 |
| 14 | alpha_beta | か | か→や | normal | 20 | 5 | 217 | 121.398 |
| 15 | beam_negamax | や | や→ぐ | danger | 3 | 5 | 312 | 60.0 |
| 16 | alpha_beta | ぐ | ぐ→う | danger | 3 | 5 | 142 | 121.587 |
| 17 | beam_negamax | う | う→え | normal | 12 | 5 | 969 | 60.0 |
| 18 | alpha_beta | え | え→う | normal | 12 | 5 | 153 | 214.02499999999998 |
| 19 | beam_negamax | う | う→む | caution | 11 | 5 | 932 | -73.07 |
| 20 | alpha_beta | む | む→う | caution | 7 | 5 | 98 | 294.51363636363635 |
| 21 | beam_negamax | う | う→の | caution | 10 | 5 | 872 | -999994.0 |
| 22 | alpha_beta | の | の→ず | danger | 5 | 5 | 111 | 999995.0 |
| 23 | beam_negamax | ず | ず→つ | near_death | 2 | 5 | 238 | -999996.0 |
| 24 | alpha_beta | つ | つ→や | normal | 8 | 5 | 80 | 999997.0 |
| 25 | beam_negamax | や | や→ど | near_death | 2 | 5 | 219 | -999998.0 |
| 26 | alpha_beta | ど | ど→る | normal | 10 | 5 | 80 | 999999.0 |

## 重要局面

- 手2、必要文字`る`、near_death、候補1、選択`る→む`、深度5、235 nodes。攻撃score -269.5、生存score 100.73333333333333。軽量順位1、上位候補: る→む(-269.5)。
- 手3、必要文字`む`、caution、候補9、選択`む→や`、深度5、1009 nodes。攻撃score -180.0、生存score 84.05。軽量順位2、上位候補: む→ら(-129.5), む→や(-180.0), む→わ(-199.0), む→つ(-320.0), む→う(-339.5)。
- 手17、必要文字`う`、normal、候補12、選択`う→え`、深度5、969 nodes。攻撃score -438.5、生存score 0.0。軽量順位6、上位候補: う→の(-150.0), う→む(-209.5), う→ぎ(-219.5), う→く(-250.0), う→り(-429.0)。
- 手19、必要文字`う`、caution、候補11、選択`う→む`、深度5、932 nodes。攻撃score -209.5、生存score 100.75。軽量順位2、上位候補: う→の(-150.0), う→む(-209.5), う→ぎ(-219.5), う→く(-250.0), う→り(-429.0)。
- 手23、必要文字`ず`、near_death、候補2、選択`ず→つ`、深度5、238 nodes。攻撃score -320.0、生存score 70.65。軽量順位1、上位候補: ず→つ(-320.0), ず→き(-557.0)。
- 手25、必要文字`や`、near_death、候補2、選択`や→ど`、深度5、219 nodes。攻撃score -329.0、生存score 22.990909090909092。軽量順位1、上位候補: や→ど(-329.0), や→り(-429.0)。
