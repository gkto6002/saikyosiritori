# D10000 ハイブリッド探索・固定局面比較

同一の保存局面、固定深度、同一時間制限で既存手法と3ハイブリッドを比較した。

- 深度: 8
- AlphaBeta/PVS候補上限: 8
- Beam幅: [8, 6, 4, 2]
- 1手制限: 1.0秒

| agent | mean sec | p95 sec | timeout | nodes | root complete | cutoff | beam pruned | research | graph order sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| beam_alpha_beta | 0.1939 | 0.3087 | 0.0% | 1861.0 | 100.0% | 607.2 | 19942.0 | 0.0% | 0.0000 |
| beam_pvs | 0.2103 | 0.3137 | 0.0% | 1894.8 | 100.0% | 703.2 | 21172.0 | 4.2% | 0.0000 |

## 図

- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/b96df43291f4/plots/mean_decision_time.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/b96df43291f4/plots/mean_nodes.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/b96df43291f4/plots/timeout_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/b96df43291f4/plots/root_completion_rate.png`
