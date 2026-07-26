# D10000 ハイブリッド探索・固定局面比較

同一の保存局面、固定深度、同一時間制限で既存手法と3ハイブリッドを比較した。

- 深度: 9
- AlphaBeta/PVS候補上限: 8
- Beam幅: [12, 8, 6, 4]
- 1手制限: 1.0秒

| agent | mean sec | p95 sec | timeout | nodes | root complete | cutoff | beam pruned | research | graph order sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| beam_alpha_beta | 1.0001 | 1.0002 | 100.0% | 7633.6 | 8.9% | 2054.4 | 63279.4 | 0.0% | 0.0000 |
| beam_pvs | 1.0002 | 1.0016 | 100.0% | 6986.6 | 10.9% | 2174.1 | 62291.6 | 1.0% | 0.0000 |

## 図

- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/051992385a78/plots/mean_decision_time.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/051992385a78/plots/mean_nodes.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/051992385a78/plots/timeout_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/051992385a78/plots/root_completion_rate.png`
