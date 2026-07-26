# D10000 ハイブリッドエージェント比較

対局は3辞書seed、先後入替、決定的組合せ1回、1手1秒で実施した。固定局面比較は全探索手法を深度5に揃えた。

## 対局集計

| agent | games | W-L-D | win | first | second | mean sec | max sec | nodes | depth | timeout |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| alpha_beta | 30 | 18-12-0 | 60.0% | 46.7% | 73.3% | 0.3647 | 1.0001 | 3503.1 | 5.98 | 62 |
| pvs | 30 | 18-12-0 | 60.0% | 60.0% | 60.0% | 0.3556 | 1.0001 | 3559.7 | 5.95 | 66 |
| beam_negamax | 30 | 9-21-0 | 30.0% | 33.3% | 26.7% | 0.4027 | 1.0001 | 5215.5 | 7.08 | 7 |
| graph_pvs | 30 | 9-21-0 | 30.0% | 26.7% | 33.3% | 0.2872 | 1.0001 | 1112.7 | 4.83 | 10 |
| beam_alpha_beta | 30 | 15-15-0 | 50.0% | 46.7% | 53.3% | 0.1021 | 0.8085 | 1167.4 | 7.97 | 0 |
| beam_pvs | 30 | 21-9-0 | 70.0% | 73.3% | 66.7% | 0.1170 | 0.8348 | 1370.1 | 7.97 | 0 |

## 同一深度・固定局面での効果

- Graph+PVS / PVS: 時間変化 +133.4%、ノード変化 +3.2%。
- Beam+AlphaBeta / Beam: 時間変化 -71.1%、ノード変化 -70.1%。
- Beam+AlphaBeta / AlphaBeta: 時間変化 -83.8%、ノード変化 -78.5%。
- Beam+PVS / Beam: 時間変化 -67.4%、ノード変化 -67.2%。
- Beam+PVS / PVS: 時間変化 -78.2%、ノード変化 -72.4%。
- Graph+PVSのGraph ordering時間は平均0.1750秒、探索ノードで先頭候補を変更した割合は14.1%。
- pvs 対局中再探索率: 0.8% (30745/4097975)。
- graph_pvs 対局中再探索率: 1.4% (15700/1108820)。
- beam_pvs 対局中再探索率: 3.4% (32848/967393)。

## 直接対戦

| left | right | games | left wins | right wins | draws |
|---|---|---:|---:|---:|---:|
| alpha_beta | pvs | 6 | 2 | 4 | 0 |
| alpha_beta | beam_negamax | 6 | 5 | 1 | 0 |
| alpha_beta | graph_pvs | 6 | 5 | 1 | 0 |
| alpha_beta | beam_alpha_beta | 6 | 4 | 2 | 0 |
| alpha_beta | beam_pvs | 6 | 2 | 4 | 0 |
| pvs | beam_negamax | 6 | 3 | 3 | 0 |
| pvs | graph_pvs | 6 | 6 | 0 | 0 |
| pvs | beam_alpha_beta | 6 | 3 | 3 | 0 |
| pvs | beam_pvs | 6 | 2 | 4 | 0 |
| beam_negamax | graph_pvs | 6 | 2 | 4 | 0 |
| beam_negamax | beam_alpha_beta | 6 | 3 | 3 | 0 |
| beam_negamax | beam_pvs | 6 | 0 | 6 | 0 |
| graph_pvs | beam_alpha_beta | 6 | 2 | 4 | 0 |
| graph_pvs | beam_pvs | 6 | 2 | 4 | 0 |
| beam_alpha_beta | beam_pvs | 6 | 3 | 3 | 0 |

## 図

- `results/agent_comparison/D10000_adaptive/1922626ea4d6/hybrid_analysis/plots/win_rate.png`
- `results/agent_comparison/D10000_adaptive/1922626ea4d6/hybrid_analysis/plots/first_win_rate.png`
- `results/agent_comparison/D10000_adaptive/1922626ea4d6/hybrid_analysis/plots/second_win_rate.png`
- `results/agent_comparison/D10000_adaptive/1922626ea4d6/hybrid_analysis/plots/mean_decision_time.png`
- `results/agent_comparison/D10000_adaptive/1922626ea4d6/hybrid_analysis/plots/mean_nodes.png`
- `results/agent_comparison/D10000_adaptive/1922626ea4d6/hybrid_analysis/plots/mean_match_turns.png`
