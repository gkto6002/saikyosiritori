# D10000 ハイブリッドエージェント比較

対局は10辞書seed、先後入替、決定的組合せ1回、1手1秒で実施した。固定局面比較は全探索手法を深度5に揃えた。

## 対局集計

| agent | games | W-L-D | win | first | second | mean sec | max sec | nodes | depth | timeout |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| alpha_beta | 60 | 32-28-0 | 53.3% | 53.3% | 53.3% | 0.3599 | 1.0006 | 3860.5 | 6.13 | 122 |
| pvs | 60 | 32-28-0 | 53.3% | 53.3% | 53.3% | 0.3524 | 1.0001 | 3530.6 | 6.05 | 114 |
| beam_alpha_beta | 60 | 30-30-0 | 50.0% | 50.0% | 50.0% | 0.0931 | 0.4483 | 1180.1 | 7.97 | 0 |
| beam_pvs | 60 | 26-34-0 | 43.3% | 43.3% | 43.3% | 0.1049 | 0.9295 | 1327.5 | 7.97 | 0 |

## 同一深度・固定局面での効果

- Graph+PVS / PVS: 時間変化 +133.4%、ノード変化 +3.2%。
- Beam+AlphaBeta / Beam: 時間変化 -71.1%、ノード変化 -70.1%。
- Beam+AlphaBeta / AlphaBeta: 時間変化 -83.8%、ノード変化 -78.5%。
- Beam+PVS / Beam: 時間変化 -67.4%、ノード変化 -67.2%。
- Beam+PVS / PVS: 時間変化 -78.2%、ノード変化 -72.4%。
- Graph+PVSのGraph ordering時間は平均0.1750秒、探索ノードで先頭候補を変更した割合は14.1%。
- pvs 対局中再探索率: 0.7% (49474/7485656)。
- beam_pvs 対局中再探索率: 3.5% (58556/1695841)。

## 直接対戦

| left | right | games | left wins | right wins | draws |
|---|---|---:|---:|---:|---:|
| alpha_beta | pvs | 20 | 10 | 10 | 0 |
| alpha_beta | beam_alpha_beta | 20 | 11 | 9 | 0 |
| alpha_beta | beam_pvs | 20 | 11 | 9 | 0 |
| pvs | beam_alpha_beta | 20 | 9 | 11 | 0 |
| pvs | beam_pvs | 20 | 13 | 7 | 0 |
| beam_alpha_beta | beam_pvs | 20 | 10 | 10 | 0 |

## 辞書seed別勝率

| seed | alpha_beta | pvs | beam_alpha_beta | beam_pvs |
|---:|---:|---:|---:|---:|
| 0 | 33.3% | 50.0% | 50.0% | 66.7% |
| 1 | 33.3% | 16.7% | 83.3% | 66.7% |
| 2 | 50.0% | 50.0% | 50.0% | 50.0% |
| 3 | 100.0% | 66.7% | 16.7% | 16.7% |
| 4 | 33.3% | 16.7% | 66.7% | 83.3% |
| 5 | 66.7% | 83.3% | 33.3% | 16.7% |
| 6 | 33.3% | 66.7% | 66.7% | 33.3% |
| 7 | 33.3% | 50.0% | 66.7% | 50.0% |
| 8 | 66.7% | 66.7% | 33.3% | 33.3% |
| 9 | 83.3% | 66.7% | 33.3% | 16.7% |

## 図

- `results/agent_comparison/D10000_adaptive/7af6b4899cda/hybrid_analysis/plots/win_rate.png`
- `results/agent_comparison/D10000_adaptive/7af6b4899cda/hybrid_analysis/plots/first_win_rate.png`
- `results/agent_comparison/D10000_adaptive/7af6b4899cda/hybrid_analysis/plots/second_win_rate.png`
- `results/agent_comparison/D10000_adaptive/7af6b4899cda/hybrid_analysis/plots/mean_decision_time.png`
- `results/agent_comparison/D10000_adaptive/7af6b4899cda/hybrid_analysis/plots/mean_nodes.png`
- `results/agent_comparison/D10000_adaptive/7af6b4899cda/hybrid_analysis/plots/mean_match_turns.png`
- `results/agent_comparison/D10000_adaptive/7af6b4899cda/hybrid_analysis/plots/win_rate_by_dictionary_seed.png`
