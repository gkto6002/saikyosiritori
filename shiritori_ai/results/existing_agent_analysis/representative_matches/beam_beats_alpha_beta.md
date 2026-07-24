# beam_beats_alpha_beta: D1000_seed0_alpha_beta_vs_beam_negamax

- D=1000 seed=0
- alpha_beta vs beam_negamax
- winner=beam_negamax turns=24

## 全手順

| 手 | AI | 必要文字 | 辺 | risk | 候補 | 深度 | nodes | score |
|---:|---|---|---|---|---:|---:|---:|---:|
| 1 | alpha_beta | ANY | お→び | normal | 640 | 5 | 492 | 237.06363636363636 |
| 2 | beam_negamax | び | び→す | near_death | 2 | 5 | 132 | 32.69250000000001 |
| 3 | alpha_beta | す | す→ぷ | normal | 18 | 5 | 866 | 121.54625 |
| 4 | beam_negamax | ぷ | ぷ→る | danger | 4 | 5 | 448 | 150.0 |
| 5 | alpha_beta | る | る→る | near_death | 2 | 5 | 231 | 150.0 |
| 6 | beam_negamax | る | る→む | near_death | 1 | 5 | 150 | 237.45636363636362 |
| 7 | alpha_beta | む | む→わ | caution | 9 | 5 | 631 | 121.12625 |
| 8 | beam_negamax | わ | わ→く | caution | 7 | 5 | 735 | 533.468 |
| 9 | alpha_beta | く | く→ぐ | caution | 7 | 5 | 395 | 129.5 |
| 10 | beam_negamax | ぐ | ぐ→か | danger | 4 | 5 | 507 | 121.12625 |
| 11 | alpha_beta | か | か→や | normal | 20 | 5 | 577 | 121.12625 |
| 12 | beam_negamax | や | や→ぐ | caution | 6 | 5 | 673 | 534.008 |
| 13 | alpha_beta | ぐ | ぐ→う | danger | 3 | 5 | 170 | 119.78800000000001 |
| 14 | beam_negamax | う | う→く | normal | 12 | 5 | 982 | 160.0 |
| 15 | alpha_beta | く | く→か | caution | 6 | 5 | 454 | 119.78800000000001 |
| 16 | beam_negamax | か | か→う | normal | 20 | 5 | 959 | 121.12625 |
| 17 | alpha_beta | う | う→の | caution | 11 | 5 | 440 | 119.78800000000001 |
| 18 | beam_negamax | の | の→ず | danger | 5 | 5 | 508 | 160.0 |
| 19 | alpha_beta | ず | ず→つ | near_death | 2 | 5 | 137 | -999994.0 |
| 20 | beam_negamax | つ | つ→く | normal | 8 | 5 | 938 | 999995.0 |
| 21 | alpha_beta | く | く→れ | caution | 5 | 5 | 77 | -999996.0 |
| 22 | beam_negamax | れ | れ→く | normal | 9 | 5 | 932 | 999997.0 |
| 23 | alpha_beta | く | く→ら | caution | 4 | 5 | 20 | -999998.0 |
| 24 | beam_negamax | ら | ら→る | danger | 5 | 5 | 291 | 999999.0 |

## 重要局面

- 手2、必要文字`び`、near_death、候補2、選択`び→す`、深度5、132 nodes。攻撃score -649.0、生存score 44.791304347826085。軽量順位1、上位候補: び→す(-649.0), び→ん(-1000000.0)。
- 手5、必要文字`る`、near_death、候補2、選択`る→る`、深度5、231 nodes。攻撃score -30.0、生存score 170.2。軽量順位1、上位候補: る→る(-30.0), る→む(-269.5)。
- 手6、必要文字`る`、near_death、候補1、選択`る→む`、深度5、150 nodes。攻撃score -269.5、生存score 100.73333333333333。軽量順位1、上位候補: る→む(-269.5)。
- 手14、必要文字`う`、normal、候補12、選択`う→く`、深度5、982 nodes。攻撃score -220.0、生存score 0.0。軽量順位3、上位候補: う→の(-150.0), う→ぎ(-219.5), う→く(-220.0), う→む(-239.5), う→り(-429.0)。
- 手16、必要文字`か`、normal、候補20、選択`か→う`、深度5、959 nodes。攻撃score -309.5、生存score 0.0。軽量順位6、上位候補: か→ら(-129.5), か→や(-150.0), か→ゆ(-250.0), か→ろ(-270.0), か→よ(-279.5)。
- 手19、必要文字`ず`、near_death、候補2、選択`ず→つ`、深度5、137 nodes。攻撃score -320.0、生存score 124.875。軽量順位1、上位候補: ず→つ(-320.0), ず→き(-557.0)。
