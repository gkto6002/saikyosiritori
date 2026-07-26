# D10000 ハイブリッド探索・固定局面比較

同一の保存局面、固定深度、同一時間制限で既存手法と3ハイブリッドを比較した。

- 深度: 9
- AlphaBeta/PVS候補上限: 8
- Beam幅: [12, 8, 4, 2]
- 1手制限: 1.0秒

| agent | mean sec | p95 sec | timeout | nodes | root complete | cutoff | beam pruned | research | graph order sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| beam_alpha_beta | 0.5015 | 1.0000 | 7.1% | 4746.6 | 98.2% | 1446.0 | 49665.3 | 0.0% | 0.0000 |
| beam_pvs | 0.6618 | 1.0001 | 28.6% | 3962.1 | 88.1% | 1495.7 | 43731.9 | 2.2% | 0.0000 |

## 図

- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/a1111bff2df7/plots/mean_decision_time.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/a1111bff2df7/plots/mean_nodes.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/a1111bff2df7/plots/timeout_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/a1111bff2df7/plots/root_completion_rate.png`
