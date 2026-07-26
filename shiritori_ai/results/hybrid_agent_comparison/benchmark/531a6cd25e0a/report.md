# D10000 ハイブリッド探索・固定局面比較

同一の保存局面、固定深度、同一時間制限で既存手法と3ハイブリッドを比較した。

- 深度: 10
- AlphaBeta/PVS候補上限: 8
- Beam幅: [12, 8, 4, 2]
- 1手制限: 1.0秒

| agent | mean sec | p95 sec | timeout | nodes | root complete | cutoff | beam pruned | research | graph order sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| beam_alpha_beta | 0.8020 | 1.0001 | 35.7% | 6176.7 | 83.3% | 2129.0 | 68981.9 | 0.0% | 0.0000 |
| beam_pvs | 0.9127 | 1.0039 | 71.4% | 4588.0 | 55.3% | 1730.6 | 52668.8 | 2.8% | 0.0000 |

## 図

- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/531a6cd25e0a/plots/mean_decision_time.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/531a6cd25e0a/plots/mean_nodes.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/531a6cd25e0a/plots/timeout_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/531a6cd25e0a/plots/root_completion_rate.png`
