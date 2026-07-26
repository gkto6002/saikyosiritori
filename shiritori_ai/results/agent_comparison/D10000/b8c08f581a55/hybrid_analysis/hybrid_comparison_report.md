# D10000 ハイブリッドエージェント比較

対局は3辞書seed、先後入替、決定的組合せ1回、1手1秒で実施した。固定局面比較は全探索手法を深度5に揃えた。

## 対局集計

| agent | games | W-L-D | win | first | second | mean sec | max sec | nodes | depth | timeout |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| alpha_beta | 36 | 26-10-0 | 72.2% | 72.2% | 72.2% | 0.1278 | 0.6199 | 1231.6 | 5.00 | 0 |
| pvs | 36 | 27-9-0 | 75.0% | 72.2% | 77.8% | 0.1310 | 0.7336 | 1285.4 | 5.00 | 0 |
| beam_negamax | 36 | 22-14-0 | 61.1% | 77.8% | 44.4% | 0.0970 | 0.2546 | 1224.9 | 5.00 | 0 |
| graph_control | 36 | 0-36-0 | 0.0% | 0.0% | 0.0% | 0.0312 | 1.0063 | 0.0 | 0.00 | 12 |
| graph_pvs | 36 | 8-28-0 | 22.2% | 22.2% | 22.2% | 0.3666 | 1.0001 | 1542.4 | 5.00 | 50 |
| beam_alpha_beta | 36 | 22-14-0 | 61.1% | 77.8% | 44.4% | 0.0234 | 0.1815 | 281.2 | 5.00 | 0 |
| beam_pvs | 36 | 21-15-0 | 58.3% | 72.2% | 44.4% | 0.0279 | 0.1816 | 343.9 | 5.00 | 0 |

## 同一深度・固定局面での効果

- Graph+PVS / PVS: 時間変化 +133.4%、ノード変化 +3.2%。
- Beam+AlphaBeta / Beam: 時間変化 -71.1%、ノード変化 -70.1%。
- Beam+AlphaBeta / AlphaBeta: 時間変化 -83.8%、ノード変化 -78.5%。
- Beam+PVS / Beam: 時間変化 -67.4%、ノード変化 -67.2%。
- Beam+PVS / PVS: 時間変化 -78.2%、ノード変化 -72.4%。
- Graph+PVSのGraph ordering時間は平均0.1750秒、探索ノードで先頭候補を変更した割合は14.1%。
- pvs 対局中再探索率: 1.3% (24146/1812116)。
- graph_pvs 対局中再探索率: 1.2% (31776/2620332)。
- beam_pvs 対局中再探索率: 5.1% (15707/306551)。

## 直接対戦

| left | right | games | left wins | right wins | draws |
|---|---|---:|---:|---:|---:|
| alpha_beta | pvs | 6 | 3 | 3 | 0 |
| alpha_beta | beam_negamax | 6 | 4 | 2 | 0 |
| alpha_beta | graph_control | 6 | 6 | 0 | 0 |
| alpha_beta | graph_pvs | 6 | 5 | 1 | 0 |
| alpha_beta | beam_alpha_beta | 6 | 4 | 2 | 0 |
| alpha_beta | beam_pvs | 6 | 4 | 2 | 0 |
| pvs | beam_negamax | 6 | 4 | 2 | 0 |
| pvs | graph_control | 6 | 6 | 0 | 0 |
| pvs | graph_pvs | 6 | 6 | 0 | 0 |
| pvs | beam_alpha_beta | 6 | 4 | 2 | 0 |
| pvs | beam_pvs | 6 | 4 | 2 | 0 |
| beam_negamax | graph_control | 6 | 6 | 0 | 0 |
| beam_negamax | graph_pvs | 6 | 6 | 0 | 0 |
| beam_negamax | beam_alpha_beta | 6 | 3 | 3 | 0 |
| beam_negamax | beam_pvs | 6 | 3 | 3 | 0 |
| graph_control | graph_pvs | 6 | 0 | 6 | 0 |
| graph_control | beam_alpha_beta | 6 | 0 | 6 | 0 |
| graph_control | beam_pvs | 6 | 0 | 6 | 0 |
| graph_pvs | beam_alpha_beta | 6 | 0 | 6 | 0 |
| graph_pvs | beam_pvs | 6 | 1 | 5 | 0 |
| beam_alpha_beta | beam_pvs | 6 | 3 | 3 | 0 |

## 図

- `results/agent_comparison/D10000/b8c08f581a55/hybrid_analysis/plots/win_rate.png`
- `results/agent_comparison/D10000/b8c08f581a55/hybrid_analysis/plots/first_win_rate.png`
- `results/agent_comparison/D10000/b8c08f581a55/hybrid_analysis/plots/second_win_rate.png`
- `results/agent_comparison/D10000/b8c08f581a55/hybrid_analysis/plots/mean_decision_time.png`
- `results/agent_comparison/D10000/b8c08f581a55/hybrid_analysis/plots/mean_nodes.png`
- `results/agent_comparison/D10000/b8c08f581a55/hybrid_analysis/plots/mean_match_turns.png`
