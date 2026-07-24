# counterfactual_changes_outcome: D3000_seed0_beam_negamax_vs_alpha_beta

- D=3000 seed=0
- beam_negamax vs alpha_beta
- winner=alpha_beta turns=38

## 全手順

| 手 | AI | 必要文字 | 辺 | risk | 候補 | 深度 | nodes | score |
|---:|---|---|---|---|---:|---:|---:|---:|
| 1 | beam_negamax | ANY | い→ぬ | normal | 1278 | 5 | 561 | 309.5 |
| 2 | alpha_beta | ぬ | ぬ→み | near_death | 2 | 5 | 1963 | 355.535 |
| 3 | beam_negamax | み | み→ぞ | normal | 25 | 5 | 1234 | 309.5 |
| 4 | alpha_beta | ぞ | ぞ→よ | caution | 7 | 5 | 1652 | 379.0 |
| 5 | beam_negamax | よ | よ→ご | normal | 16 | 5 | 1393 | 357.4371428571428 |
| 6 | alpha_beta | ご | ご→う | normal | 9 | 5 | 1239 | 379.0 |
| 7 | beam_negamax | う | う→ら | normal | 25 | 5 | 1393 | 309.5 |
| 8 | alpha_beta | ら | ら→る | normal | 12 | 5 | 1201 | 379.0 |
| 9 | beam_negamax | る | る→る | danger | 4 | 5 | 606 | 309.5 |
| 10 | alpha_beta | る | る→む | danger | 3 | 5 | 1082 | 379.0 |
| 11 | beam_negamax | む | む→わ | normal | 12 | 5 | 1370 | 379.0 |
| 12 | alpha_beta | わ | わ→ぐ | normal | 15 | 5 | 502 | 418.5 |
| 13 | beam_negamax | ぐ | ぐ→む | caution | 11 | 5 | 1318 | 379.0 |
| 14 | alpha_beta | む | む→ぐ | normal | 11 | 5 | 727 | 428.5 |
| 15 | beam_negamax | ぐ | ぐ→ぷ | caution | 10 | 5 | 1303 | 379.0 |
| 16 | alpha_beta | ぷ | ぷ→む | normal | 10 | 5 | 651 | 428.5 |
| 17 | beam_negamax | む | む→ら | normal | 10 | 5 | 1340 | 418.5 |
| 18 | alpha_beta | ら | ら→ぐ | normal | 11 | 5 | 564 | 448.5 |
| 19 | beam_negamax | ぐ | ぐ→ろ | caution | 9 | 5 | 1325 | 418.5 |
| 20 | alpha_beta | ろ | ろ→る | normal | 14 | 5 | 556 | 458.5 |
| 21 | beam_negamax | る | る→う | near_death | 2 | 5 | 302 | 558.0 |
| 22 | alpha_beta | う | う→む | normal | 24 | 5 | 782 | 419.5 |
| 23 | beam_negamax | む | む→う | normal | 9 | 5 | 1195 | 558.0 |
| 24 | alpha_beta | う | う→や | normal | 23 | 5 | 1006 | 419.5 |
| 25 | beam_negamax | や | や→わ | normal | 18 | 5 | 1243 | 454.8034482758621 |
| 26 | alpha_beta | わ | わ→ら | normal | 14 | 5 | 526 | 448.5 |
| 27 | beam_negamax | ら | ら→つ | normal | 11 | 5 | 1191 | 428.5 |
| 28 | alpha_beta | つ | つ→う | normal | 21 | 5 | 1193 | 488.5 |
| 29 | beam_negamax | う | う→け | normal | 22 | 5 | 1163 | 488.5 |
| 30 | alpha_beta | け | け→う | normal | 17 | 5 | 899 | 488.5 |
| 31 | beam_negamax | う | う→つ | normal | 21 | 5 | 1137 | 428.5 |
| 32 | alpha_beta | つ | つ→わ | normal | 20 | 5 | 1840 | 30.0 |
| 33 | beam_negamax | わ | わ→や | normal | 13 | 5 | 1193 | 488.5 |
| 34 | alpha_beta | や | や→う | normal | 17 | 5 | 1216 | 999995.0 |
| 35 | beam_negamax | う | う→の | normal | 20 | 5 | 1106 | -999996.0 |
| 36 | alpha_beta | の | の→る | normal | 11 | 5 | 238 | 999997.0 |
| 37 | beam_negamax | る | る→ゆ | near_death | 1 | 5 | 123 | -999998.0 |
| 38 | alpha_beta | ゆ | ゆ→る | normal | 19 | 5 | 215 | 999999.0 |

## 重要局面

- 手2、必要文字`ぬ`、near_death、候補2、選択`ぬ→み`、深度5、1963 nodes。攻撃score -1308.5、生存score 131.87884615384615。軽量順位2、上位候補: ぬ→ど(-798.0), ぬ→み(-1308.5)。
- 手4、必要文字`ぞ`、caution、候補7、選択`ぞ→よ`、深度5、1652 nodes。攻撃score -716.5、生存score 253.14。軽量順位1、上位候補: ぞ→よ(-716.5), ぞ→つ(-818.0), ぞ→う(-988.5), ぞ→く(-1407.0), ぞ→き(-1963.5)。
- 手5、必要文字`よ`、normal、候補16、選択`よ→ご`、深度5、1393 nodes。攻撃score -417.0、生存score 0.0。軽量順位1、上位候補: よ→ご(-417.0), よ→び(-448.5), よ→れ(-628.0), よ→で(-767.0), よ→う(-988.5)。
- 手21、必要文字`る`、near_death、候補2、選択`る→う`、深度5、302 nodes。攻撃score -958.5、生存score 269.86857142857144。軽量順位2、上位候補: る→ゆ(-948.5), る→う(-958.5)。
- 手32、必要文字`つ`、normal、候補20、選択`つ→わ`、深度5、1840 nodes。攻撃score -438.0、生存score 0.0。軽量順位2、上位候補: つ→ぜ(-418.5), つ→わ(-438.0), つ→ろ(-488.5), つ→や(-558.0), つ→ぎ(-618.5)。
- 手37、必要文字`る`、near_death、候補1、選択`る→ゆ`、深度5、123 nodes。攻撃score -948.5、生存score 73.62162162162163。軽量順位1、上位候補: る→ゆ(-948.5)。
