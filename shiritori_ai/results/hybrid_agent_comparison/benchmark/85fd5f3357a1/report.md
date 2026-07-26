# D10000 ハイブリッド探索・固定局面比較

同一の保存局面、固定深度、同一時間制限で既存手法と3ハイブリッドを比較した。

- 深度: 9
- AlphaBeta/PVS候補上限: 8
- Beam幅: [8, 6, 4, 2]
- 1手制限: 1.0秒

| agent | mean sec | p95 sec | timeout | nodes | root complete | cutoff | beam pruned | research | graph order sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| beam_alpha_beta | 0.3694 | 0.7821 | 0.0% | 3442.4 | 100.0% | 1029.1 | 36015.6 | 0.0% | 0.0000 |
| beam_pvs | 0.4318 | 0.8865 | 0.0% | 3559.1 | 100.0% | 1323.2 | 39217.6 | 2.8% | 0.0000 |

## 図

- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/85fd5f3357a1/plots/mean_decision_time.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/85fd5f3357a1/plots/mean_nodes.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/85fd5f3357a1/plots/timeout_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/85fd5f3357a1/plots/root_completion_rate.png`
