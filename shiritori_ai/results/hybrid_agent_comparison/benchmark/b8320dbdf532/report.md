# D10000 ハイブリッド探索・固定局面比較

同一の保存局面、固定深度、同一時間制限で既存手法と3ハイブリッドを比較した。

- 深度: 6
- AlphaBeta/PVS候補上限: 8
- Beam幅: [8, 6, 4, 2]
- 1手制限: 1.0秒

| agent | mean sec | p95 sec | timeout | nodes | root complete | cutoff | beam pruned | research | graph order sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| alpha_beta | 0.8009 | 1.0001 | 42.9% | 4686.4 | 79.5% | 1065.9 | 0.0 | 0.0% | 0.0000 |
| beam_alpha_beta | 0.0760 | 0.1082 | 0.0% | 616.8 | 100.0% | 195.5 | 6490.8 | 0.0% | 0.0000 |
| beam_negamax | 0.3136 | 0.3740 | 0.0% | 2831.1 | 100.0% | 0.0 | 22449.1 | 0.0% | 0.0000 |
| beam_pvs | 0.0790 | 0.1385 | 0.0% | 633.3 | 100.0% | 224.6 | 6753.6 | 5.1% | 0.0000 |
| pvs | 0.7394 | 1.0001 | 7.1% | 4917.2 | 95.5% | 1161.1 | 0.0 | 0.6% | 0.0000 |

## 図

- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/b8320dbdf532/plots/mean_decision_time.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/b8320dbdf532/plots/mean_nodes.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/b8320dbdf532/plots/timeout_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/b8320dbdf532/plots/root_completion_rate.png`
