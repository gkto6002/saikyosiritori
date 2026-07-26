# Full AlphaBetaとSelective AlphaBetaの比較

Full AlphaBetaは各plyの全合法辺を対象にし、Selective AlphaBetaは評価上位だけを対象にする。どちらも固定深度で、評価関数とAlphaBeta枝刈りは共通である。

- 1手制限: 1.0秒
- 局面ファイル: `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/search_parameter_tuning/f5a877380b91/fixed_positions.json`

## 固定局面ベンチマーク

| config | depth | branch | mean sec | p95 sec | timeout | mean nodes | root completion |
|---|---:|---:|---:|---:|---:|---:|---:|
| full_alpha_beta_d3 | 3 | all | 0.2619 | 1.0001 | 21.4% | 2562.1 | 83.4% |
| full_alpha_beta_d4 | 4 | all | 0.3564 | 1.0000 | 21.4% | 4508.8 | 81.8% |
| full_alpha_beta_d5 | 5 | all | 0.6957 | 1.0000 | 50.0% | 7221.9 | 58.8% |
| selective_alpha_beta_d3_b12 | 3 | 12 | 0.0237 | 0.0376 | 0.0% | 251.4 | 100.0% |
| selective_alpha_beta_d3_b16 | 3 | 16 | 0.0346 | 0.0558 | 0.0% | 379.4 | 100.0% |
| selective_alpha_beta_d3_b8 | 3 | 8 | 0.0149 | 0.0218 | 0.0% | 159.9 | 100.0% |
| selective_alpha_beta_d4_b12 | 4 | 12 | 0.0818 | 0.1675 | 0.0% | 998.9 | 100.0% |
| selective_alpha_beta_d4_b16 | 4 | 16 | 0.1087 | 0.2362 | 0.0% | 1326.9 | 100.0% |
| selective_alpha_beta_d4_b8 | 4 | 8 | 0.0424 | 0.0631 | 0.0% | 516.6 | 100.0% |
| selective_alpha_beta_d5_b12 | 5 | 12 | 0.3615 | 0.9296 | 0.0% | 4159.6 | 100.0% |
| selective_alpha_beta_d5_b16 | 5 | 16 | 0.5322 | 1.0000 | 7.1% | 6042.6 | 96.0% |
| selective_alpha_beta_d5_b8 | 5 | 8 | 0.1642 | 0.2355 | 0.0% | 1881.6 | 100.0% |

## Fullとの一致

Fullが制限時間内にルート全候補を完了した局面だけを、手と評価値の参照比較に使用する。

| depth | branch | Full完了 | 比較可能 | 手一致 | 評価一致 | Selective速度倍率 |
|---:|---:|---:|---:|---:|---:|---:|
| 3 | 8 | 11/14 | 11 | 72.7% | 63.6% | 16.74x |
| 3 | 12 | 11/14 | 11 | 72.7% | 63.6% | 9.31x |
| 3 | 16 | 11/14 | 11 | 81.8% | 81.8% | 6.31x |
| 4 | 8 | 11/14 | 11 | 63.6% | 63.6% | 7.96x |
| 4 | 12 | 11/14 | 11 | 100.0% | 72.7% | 4.22x |
| 4 | 16 | 11/14 | 11 | 100.0% | 81.8% | 3.26x |
| 5 | 8 | 7/14 | 7 | 85.7% | 42.9% | 4.09x |
| 5 | 12 | 7/14 | 7 | 71.4% | 42.9% | 2.07x |
| 5 | 16 | 7/14 | 7 | 71.4% | 57.1% | 1.45x |

## 対局

| agent | games | wins | losses | draws | win rate | mean sec | timeout |
|---|---:|---:|---:|---:|---:|---:|---:|
| full_alpha_beta | 6 | 3 | 3 | 0 | 50.0% | 0.1744 | 3 |
| selective_alpha_beta | 6 | 3 | 3 | 0 | 50.0% | 0.0322 | 0 |

## 図

- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/full_alpha_beta_comparison/6e27f4a5f481/plots/mean_decision_time.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/full_alpha_beta_comparison/6e27f4a5f481/plots/mean_nodes.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/full_alpha_beta_comparison/6e27f4a5f481/plots/full_completion_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/full_alpha_beta_comparison/6e27f4a5f481/plots/move_agreement_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/full_alpha_beta_comparison/6e27f4a5f481/plots/match_win_rate.png`
