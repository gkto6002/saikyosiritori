# D10000 ハイブリッド探索・固定局面比較

同一の保存局面、固定深度、同一時間制限で既存手法と3ハイブリッドを比較した。

- 深度: 5
- AlphaBeta/PVS候補上限: 8
- Beam幅: [8, 6, 4, 2]
- 1手制限: 1.0秒

| agent | mean sec | p95 sec | timeout | nodes | root complete | cutoff | beam pruned | research | graph order sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| alpha_beta | 0.1631 | 0.2397 | 0.0% | 1881.6 | 100.0% | 300.9 | 0.0 | 0.0% | 0.0000 |
| beam_alpha_beta | 0.0265 | 0.0410 | 0.0% | 403.9 | 100.0% | 97.3 | 4039.2 | 0.0% | 0.0000 |
| beam_negamax | 0.0917 | 0.1191 | 0.0% | 1350.0 | 100.0% | 0.0 | 10556.5 | 0.0% | 0.0000 |
| beam_pvs | 0.0299 | 0.0421 | 0.0% | 443.0 | 100.0% | 140.4 | 4521.9 | 5.5% | 0.0000 |
| graph_control | 0.2065 | 0.9154 | 0.0% | 0.0 | 100.0% | 0.0 | 0.0 | 0.0% | 0.0000 |
| graph_pvs | 0.3202 | 0.6649 | 0.0% | 1655.6 | 100.0% | 363.6 | 0.0 | 1.4% | 0.1750 |
| pvs | 0.1372 | 0.2250 | 0.0% | 1605.1 | 100.0% | 353.3 | 0.0 | 1.1% | 0.0000 |

## 図

- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/821264dd868d/plots/mean_decision_time.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/821264dd868d/plots/mean_nodes.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/821264dd868d/plots/timeout_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/hybrid_agent_comparison/benchmark/821264dd868d/plots/root_completion_rate.png`
