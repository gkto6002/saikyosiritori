# D10000 ハイブリッド探索・固定局面比較

同一の保存局面、固定深度、同一時間制限で既存手法と3ハイブリッドを比較した。

- 深度: 10
- AlphaBeta/PVS候補上限: 8
- Beam幅: [8, 6, 4, 2]
- 1手制限: 1.0秒

| agent | mean sec | p95 sec | timeout | nodes | root complete | cutoff | beam pruned | research | graph order sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| beam_alpha_beta | 0.6040 | 1.0000 | 7.1% | 5157.2 | 99.1% | 1772.6 | 57865.0 | 0.0% | 0.0000 |
| beam_pvs | 0.6819 | 1.0059 | 42.9% | 5126.8 | 89.3% | 1949.7 | 59796.3 | 2.9% | 0.0000 |

## 図

- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/93c542ffd458/plots/mean_decision_time.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/93c542ffd458/plots/mean_nodes.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/93c542ffd458/plots/timeout_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/93c542ffd458/plots/root_completion_rate.png`
