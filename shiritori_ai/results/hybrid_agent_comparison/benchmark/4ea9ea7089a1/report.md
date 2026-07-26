# D10000 ハイブリッド探索・固定局面比較

同一の保存局面、固定深度、同一時間制限で既存手法と3ハイブリッドを比較した。

- 深度: 7
- AlphaBeta/PVS候補上限: 8
- Beam幅: [8, 6, 4, 2]
- 1手制限: 1.0秒

| agent | mean sec | p95 sec | timeout | nodes | root complete | cutoff | beam pruned | research | graph order sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| beam_alpha_beta | 0.1905 | 0.3491 | 0.0% | 1124.4 | 100.0% | 295.6 | 11003.8 | 0.0% | 0.0000 |
| beam_negamax | 0.3744 | 0.4829 | 0.0% | 5793.4 | 100.0% | 0.0 | 45509.6 | 0.0% | 0.0000 |
| beam_pvs | 0.1872 | 0.4054 | 0.0% | 1273.5 | 100.0% | 431.4 | 12988.1 | 5.3% | 0.0000 |

## 図

- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/4ea9ea7089a1/plots/mean_decision_time.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/4ea9ea7089a1/plots/mean_nodes.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/4ea9ea7089a1/plots/timeout_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/4ea9ea7089a1/plots/root_completion_rate.png`
