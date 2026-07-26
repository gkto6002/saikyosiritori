# D10000 ハイブリッド探索・固定局面比較

同一の保存局面、固定深度、同一時間制限で既存手法と3ハイブリッドを比較した。

- 深度: 10
- AlphaBeta/PVS候補上限: 8
- Beam幅: [12, 8, 6, 4]
- 1手制限: 1.0秒

| agent | mean sec | p95 sec | timeout | nodes | root complete | cutoff | beam pruned | research | graph order sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| beam_alpha_beta | 1.0001 | 1.0002 | 100.0% | 7245.6 | 0.0% | 1954.3 | 62092.6 | 0.0% | 0.0000 |
| beam_pvs | 1.0003 | 1.0026 | 100.0% | 6506.5 | 0.0% | 1982.9 | 58904.1 | 1.2% | 0.0000 |

## 図

- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/851a9b8aee8f/plots/mean_decision_time.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/851a9b8aee8f/plots/mean_nodes.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/851a9b8aee8f/plots/timeout_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/851a9b8aee8f/plots/root_completion_rate.png`
