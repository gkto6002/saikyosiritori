# D10000 ハイブリッド探索・固定局面比較

同一の保存局面、固定深度、同一時間制限で既存手法と3ハイブリッドを比較した。

- 深度: 8
- AlphaBeta/PVS候補上限: 8
- Beam幅: [12, 8, 4, 2]
- 1手制限: 1.0秒

| agent | mean sec | p95 sec | timeout | nodes | root complete | cutoff | beam pruned | research | graph order sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| beam_alpha_beta | 0.2502 | 0.5938 | 0.0% | 2694.3 | 100.0% | 904.1 | 28599.7 | 0.0% | 0.0000 |
| beam_pvs | 0.3425 | 0.6075 | 0.0% | 2583.3 | 100.0% | 974.9 | 28471.9 | 3.2% | 0.0000 |

## 図

- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/f856ddb4eba8/plots/mean_decision_time.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/f856ddb4eba8/plots/mean_nodes.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/f856ddb4eba8/plots/timeout_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/f856ddb4eba8/plots/root_completion_rate.png`
