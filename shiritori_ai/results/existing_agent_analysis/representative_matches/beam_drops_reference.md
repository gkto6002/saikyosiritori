# beam_drops_reference: D10000_seed0_alpha_beta_vs_beam_negamax

- D=10000 seed=0
- alpha_beta vs beam_negamax
- winner=alpha_beta turns=112

## 全手順

| 手 | AI | 必要文字 | 辺 | risk | 候補 | 深度 | nodes | score |
|---:|---|---|---|---|---:|---:|---:|---:|
| 1 | alpha_beta | ANY | ず→ず | normal | 2248 | 5 | 1577 | 449.5 |
| 2 | beam_negamax | ず | ず→れ | caution | 10 | 5 | 1400 | 429.5 |
| 3 | alpha_beta | れ | れ→ず | normal | 28 | 5 | 1253 | 449.5 |
| 4 | beam_negamax | ず | ず→ち | caution | 9 | 5 | 1400 | 429.5 |
| 5 | alpha_beta | ち | ち→ず | normal | 39 | 5 | 1087 | 449.5 |
| 6 | beam_negamax | ず | ず→い | caution | 8 | 5 | 1225 | 429.5 |
| 7 | alpha_beta | い | い→ざ | normal | 47 | 5 | 1287 | 449.5 |
| 8 | beam_negamax | ざ | ざ→む | normal | 12 | 5 | 1400 | 429.5 |
| 9 | alpha_beta | む | む→ず | normal | 24 | 5 | 1073 | 734.0 |
| 10 | beam_negamax | ず | ず→む | caution | 7 | 5 | 1050 | 429.5 |
| 11 | alpha_beta | む | む→め | normal | 23 | 5 | 2200 | 1248.0 |
| 12 | beam_negamax | め | め→む | normal | 29 | 5 | 1400 | 429.5 |
| 13 | alpha_beta | む | む→め | normal | 23 | 5 | 1681 | 1135.5 |
| 14 | beam_negamax | め | め→ぎ | normal | 28 | 5 | 1400 | 429.5 |
| 15 | alpha_beta | ぎ | ぎ→ざ | normal | 32 | 5 | 1923 | 1135.5 |
| 16 | beam_negamax | ざ | ざ→い | normal | 11 | 5 | 1400 | 429.5 |
| 17 | alpha_beta | い | い→ぬ | normal | 47 | 5 | 1044 | 1248.0 |
| 18 | beam_negamax | ぬ | ぬ→ど | caution | 8 | 5 | 1400 | 429.5 |
| 19 | alpha_beta | ど | ど→む | normal | 30 | 5 | 2174 | 1135.5 |
| 20 | beam_negamax | む | む→ぐ | normal | 22 | 5 | 1400 | 429.5 |
| 21 | alpha_beta | ぐ | ぐ→つ | normal | 24 | 5 | 2945 | 1645.5 |
| 22 | beam_negamax | つ | つ→ぐ | normal | 38 | 5 | 1400 | 449.5 |
| 23 | alpha_beta | ぐ | ぐ→ぶ | normal | 23 | 5 | 2982 | 1635.5 |
| 24 | beam_negamax | ぶ | ぶ→ぐ | normal | 31 | 5 | 1400 | 449.5 |
| 25 | alpha_beta | ぐ | ぐ→ぶ | normal | 23 | 5 | 2984 | 1635.5 |
| 26 | beam_negamax | ぶ | ぶ→ぐ | normal | 31 | 5 | 1400 | 449.5 |
| 27 | alpha_beta | ぐ | ぐ→ど | normal | 22 | 5 | 2793 | 1195.5 |
| 28 | beam_negamax | ど | ど→ぐ | normal | 30 | 5 | 1400 | 449.5 |
| 29 | alpha_beta | ぐ | ぐ→ど | normal | 22 | 5 | 2793 | 1195.5 |
| 30 | beam_negamax | ど | ど→ぐ | normal | 30 | 5 | 1400 | 449.5 |
| 31 | alpha_beta | ぐ | ぐ→ど | normal | 22 | 5 | 2793 | 1195.5 |
| 32 | beam_negamax | ど | ど→ぐ | normal | 30 | 5 | 1400 | 449.5 |
| 33 | alpha_beta | ぐ | ぐ→ど | normal | 22 | 5 | 2763 | 1195.5 |
| 34 | beam_negamax | ど | ど→ら | normal | 29 | 5 | 1400 | 449.5 |
| 35 | alpha_beta | ら | ら→つ | normal | 26 | 5 | 2100 | 1635.5 |
| 36 | beam_negamax | つ | つ→ぐ | normal | 38 | 5 | 1400 | 449.5 |
| 37 | alpha_beta | ぐ | ぐ→む | normal | 21 | 5 | 2226 | 1135.5 |
| 38 | beam_negamax | む | む→ら | normal | 21 | 5 | 1400 | 449.5 |
| 39 | alpha_beta | ら | ら→つ | normal | 26 | 5 | 2011 | 1615.5 |
| 40 | beam_negamax | つ | つ→び | normal | 37 | 5 | 1400 | 429.5 |
| 41 | alpha_beta | び | び→ご | normal | 24 | 5 | 2008 | 1195.5 |
| 42 | beam_negamax | ご | ご→ら | normal | 23 | 5 | 1400 | 449.5 |
| 43 | alpha_beta | ら | ら→つ | normal | 26 | 5 | 1881 | 1585.5 |
| 44 | beam_negamax | つ | つ→ぎ | normal | 36 | 5 | 1400 | 429.5 |
| 45 | alpha_beta | ぎ | ぎ→ざ | normal | 32 | 5 | 1867 | 1195.5 |
| 46 | beam_negamax | ざ | ざ→う | normal | 11 | 5 | 1400 | 429.5 |
| 47 | alpha_beta | う | う→ず | normal | 43 | 5 | 2035 | 1195.5 |
| 48 | beam_negamax | ず | ず→う | danger | 6 | 5 | 875 | 449.5 |
| 49 | alpha_beta | う | う→ぐ | normal | 42 | 5 | 2267 | 1195.5 |
| 50 | beam_negamax | ぐ | ぐ→ら | normal | 21 | 5 | 1400 | 449.5 |
| 51 | alpha_beta | ら | ら→ぶ | normal | 25 | 5 | 2456 | 1535.5 |
| 52 | beam_negamax | ぶ | ぶ→ぐ | normal | 31 | 5 | 1400 | 449.5 |
| 53 | alpha_beta | ぐ | ぐ→む | normal | 20 | 5 | 1783 | 1195.5 |
| 54 | beam_negamax | む | む→ば | normal | 20 | 5 | 1400 | 449.5 |
| 55 | alpha_beta | ば | ば→つ | normal | 31 | 5 | 2096 | 1555.5 |
| 56 | beam_negamax | つ | つ→ぎ | normal | 36 | 5 | 1400 | 429.5 |
| 57 | alpha_beta | ぎ | ぎ→る | normal | 31 | 5 | 1624 | 1195.5 |
| 58 | beam_negamax | る | る→ぷ | normal | 13 | 5 | 1400 | 419.5 |
| 59 | alpha_beta | ぷ | ぷ→る | normal | 18 | 5 | 2039 | 1175.5 |
| 60 | beam_negamax | る | る→つ | normal | 12 | 5 | 1400 | 1574.0 |
| 61 | alpha_beta | つ | つ→る | normal | 36 | 5 | 1103 | 1275.5 |
| 62 | beam_negamax | る | る→る | normal | 11 | 5 | 1400 | 1162.0 |
| 63 | alpha_beta | る | る→る | normal | 11 | 5 | 1451 | 1275.5 |
| 64 | beam_negamax | る | る→る | normal | 11 | 5 | 1400 | 1162.0 |
| 65 | alpha_beta | る | る→ゆ | normal | 10 | 5 | 1608 | 1275.5 |
| 66 | beam_negamax | ゆ | ゆ→べ | normal | 36 | 5 | 1342 | 1574.0 |
| 67 | alpha_beta | べ | べ→つ | normal | 25 | 5 | 1769 | 1554.0 |
| 68 | beam_negamax | つ | つ→ぜ | normal | 35 | 5 | 1400 | 1255.5 |
| 69 | alpha_beta | ぜ | ぜ→ら | normal | 14 | 5 | 1633 | 1275.5 |
| 70 | beam_negamax | ら | ら→め | normal | 24 | 5 | 1400 | 1509.7571428571428 |
| 71 | alpha_beta | め | め→る | normal | 27 | 5 | 1637 | 1275.5 |
| 72 | beam_negamax | る | る→ゆ | caution | 10 | 5 | 1400 | 1275.5 |
| 73 | alpha_beta | ゆ | ゆ→ず | normal | 35 | 5 | 1375 | 1275.5 |
| 74 | beam_negamax | ず | ず→つ | danger | 5 | 5 | 679 | 1574.0 |
| 75 | alpha_beta | つ | つ→ぎ | normal | 34 | 5 | 691 | 1275.5 |
| 76 | beam_negamax | ぎ | ぎ→ぐ | normal | 30 | 5 | 1379 | 1554.0 |
| 77 | alpha_beta | ぐ | ぐ→る | normal | 20 | 5 | 756 | 1275.5 |
| 78 | beam_negamax | る | る→な | caution | 9 | 5 | 1379 | 1554.0 |
| 79 | alpha_beta | な | な→る | normal | 39 | 5 | 1028 | 1275.5 |
| 80 | beam_negamax | る | る→い | caution | 8 | 5 | 1204 | 1554.0 |
| 81 | alpha_beta | い | い→る | normal | 46 | 5 | 942 | 1275.5 |
| 82 | beam_negamax | る | る→う | caution | 7 | 5 | 1029 | 1524.0 |
| 83 | alpha_beta | う | う→る | normal | 41 | 5 | 724 | 1275.5 |
| 84 | beam_negamax | る | る→む | caution | 6 | 5 | 854 | 1275.5 |
| 85 | alpha_beta | む | む→ぎ | normal | 19 | 5 | 1278 | 1275.5 |
| 86 | beam_negamax | ぎ | ぎ→や | normal | 29 | 5 | 1372 | 1775.0 |
| 87 | alpha_beta | や | や→ざ | normal | 33 | 5 | 738 | 1275.5 |
| 88 | beam_negamax | ざ | ざ→う | normal | 11 | 5 | 1365 | 1175.5 |
| 89 | alpha_beta | う | う→む | normal | 40 | 5 | 1066 | 1275.5 |
| 90 | beam_negamax | む | む→や | normal | 19 | 5 | 1379 | 1175.5 |
| 91 | alpha_beta | や | や→む | normal | 32 | 5 | 1137 | 1275.5 |
| 92 | beam_negamax | む | む→や | normal | 19 | 5 | 1379 | 1175.5 |
| 93 | alpha_beta | や | や→ぎ | normal | 31 | 5 | 1068 | 1275.5 |
| 94 | beam_negamax | ぎ | ぎ→ぎ | normal | 29 | 5 | 1372 | 1175.5 |
| 95 | alpha_beta | ぎ | ぎ→む | normal | 28 | 5 | 1048 | 1275.5 |
| 96 | beam_negamax | む | む→つ | normal | 19 | 5 | 1379 | 1175.5 |
| 97 | alpha_beta | つ | つ→つ | normal | 33 | 5 | 908 | 2479.7715384615385 |
| 98 | beam_negamax | つ | つ→や | normal | 32 | 5 | 1365 | 149.5 |
| 99 | alpha_beta | や | や→つ | normal | 31 | 5 | 1474 | 4093.53010989011 |
| 100 | beam_negamax | つ | つ→ば | normal | 31 | 5 | 1365 | 99.5 |
| 101 | alpha_beta | ば | ば→る | normal | 31 | 5 | 320 | 4108.10945054945 |
| 102 | beam_negamax | る | る→と | danger | 5 | 5 | 658 | 69.5 |
| 103 | alpha_beta | と | と→る | normal | 43 | 5 | 498 | 4108.125274725275 |
| 104 | beam_negamax | る | る→と | danger | 5 | 5 | 651 | 39.5 |
| 105 | alpha_beta | と | と→る | normal | 43 | 5 | 531 | 4705.488317757009 |
| 106 | beam_negamax | る | る→す | danger | 4 | 5 | 456 | -999994.0 |
| 107 | alpha_beta | す | す→る | normal | 43 | 5 | 239 | 999995.0 |
| 108 | beam_negamax | る | る→あ | near_death | 3 | 5 | 249 | -999996.0 |
| 109 | alpha_beta | あ | あ→る | normal | 50 | 5 | 154 | 999997.0 |
| 110 | beam_negamax | る | る→き | near_death | 2 | 5 | 98 | -999998.0 |
| 111 | alpha_beta | き | き→る | normal | 52 | 5 | 85 | 999999.0 |
| 112 | beam_negamax | る | る→ん | near_death | 1 | 5 | 0 | -1000000.0 |

## 重要局面

- 手21、必要文字`ぐ`、normal、候補24、選択`ぐ→つ`、深度5、2945 nodes。攻撃score -2247.0、生存score 0.0。軽量順位7、上位候補: ぐ→る(-449.5), ぐ→ぷ(-1195.5), ぐ→む(-1493.0), ぐ→ら(-1655.5), ぐ→ろ(-1665.5)。
- 手23、必要文字`ぐ`、normal、候補23、選択`ぐ→ぶ`、深度5、2982 nodes。攻撃score -2510.0、生存score 0.0。軽量順位7、上位候補: ぐ→る(-449.5), ぐ→ぷ(-1195.5), ぐ→む(-1493.0), ぐ→ら(-1655.5), ぐ→ろ(-1665.5)。
- 手25、必要文字`ぐ`、normal、候補23、選択`ぐ→ぶ`、深度5、2984 nodes。攻撃score -2490.0、生存score 0.0。軽量順位7、上位候補: ぐ→る(-449.5), ぐ→ぷ(-1195.5), ぐ→む(-1493.0), ぐ→ら(-1655.5), ぐ→ろ(-1665.5)。
- 手108、必要文字`る`、near_death、候補3、選択`る→あ`、深度5、249 nodes。攻撃score -5439.0、生存score 198.77468354430377。軽量順位1、上位候補: る→あ(-5439.0), る→き(-6868.5), る→ん(-1000000.0)。
- 手110、必要文字`る`、near_death、候補2、選択`る→き`、深度5、98 nodes。攻撃score -6868.5、生存score 169.06354166666668。軽量順位1、上位候補: る→き(-6868.5), る→ん(-1000000.0)。
- 手112、必要文字`る`、near_death、候補1、選択`る→ん`、深度5、0 nodes。攻撃score -1000000.0、生存score 0.0。軽量順位1、上位候補: る→ん(-1000000.0)。
