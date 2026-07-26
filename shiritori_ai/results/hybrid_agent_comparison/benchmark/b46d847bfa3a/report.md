# D10000 ハイブリッド探索・固定局面比較

同一の保存局面、固定深度、同一時間制限で既存手法と3ハイブリッドを比較した。

- 深度: 8
- AlphaBeta/PVS候補上限: 8
- Beam幅: [12, 8, 6, 4]
- 1手制限: 1.0秒

| agent | mean sec | p95 sec | timeout | nodes | root complete | cutoff | beam pruned | research | graph order sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| beam_alpha_beta | 1.0001 | 1.0002 | 100.0% | 7969.1 | 30.7% | 2137.2 | 63713.9 | 0.0% | 0.0000 |
| beam_pvs | 0.9992 | 1.0071 | 92.9% | 7251.4 | 26.7% | 2124.2 | 59116.6 | 1.1% | 0.0000 |

## 図

- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/b46d847bfa3a/plots/mean_decision_time.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/b46d847bfa3a/plots/mean_nodes.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/b46d847bfa3a/plots/timeout_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/b46d847bfa3a/plots/root_completion_rate.png`
