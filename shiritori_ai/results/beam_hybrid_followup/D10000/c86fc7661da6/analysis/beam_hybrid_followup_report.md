# Beamハイブリッド深度・幅追試

AlphaBetaの採用済み適応設定を基準に、BeamAlphaBetaとBeamPVSの現行、深度増加、幅増加、深度+幅増加を先後入替で比較した。

- 辞書サイズ: D10000
- 辞書seed: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
- 1手制限: 1.0秒
- AlphaBeta: 初期深度5、最大深度7、branch 8

## 設定と対局結果

| config | depth | max | widths | W-L-D | win | first | second | sec | nodes | effective depth | timeout | research |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| beam_alpha_beta_baseline | 7 | 8 | 8-6-4-2 | 10-10-0 | 50.0% | 40.0% | 60.0% | 0.1048 | 1229.0 | 7.97 | 0.0% | 0.0% |
| beam_alpha_beta_deep | 8 | 9 | 8-6-4-2 | 4-16-0 | 20.0% | 10.0% | 30.0% | 0.1506 | 1867.9 | 8.96 | 0.0% | 0.0% |
| beam_alpha_beta_deep_wide | 8 | 9 | 12-8-4-2 | 16-4-0 | 80.0% | 70.0% | 90.0% | 0.2003 | 2677.4 | 8.92 | 0.2% | 0.0% |
| beam_alpha_beta_wide | 7 | 8 | 12-8-4-2 | 8-12-0 | 40.0% | 40.0% | 40.0% | 0.1321 | 1682.5 | 7.97 | 0.0% | 0.0% |
| beam_pvs_baseline | 7 | 8 | 8-6-4-2 | 13-7-0 | 65.0% | 60.0% | 70.0% | 0.1171 | 1394.6 | 7.97 | 0.0% | 3.4% |
| beam_pvs_deep | 8 | 9 | 8-6-4-2 | 9-11-0 | 45.0% | 30.0% | 60.0% | 0.1602 | 1925.3 | 8.95 | 0.0% | 2.8% |
| beam_pvs_deep_wide | 8 | 9 | 12-8-4-2 | 14-6-0 | 70.0% | 70.0% | 70.0% | 0.1917 | 2540.8 | 8.88 | 0.1% | 2.5% |
| beam_pvs_wide | 7 | 8 | 12-8-4-2 | 10-10-0 | 50.0% | 70.0% | 30.0% | 0.1592 | 1909.6 | 7.96 | 0.0% | 2.6% |

勝率50%を超えた設定だけが、この実験内でAlphaBetaへ勝ち越した設定である。
差が小さい場合は辞書seed別結果と速度・タイムアウトも合わせて判断する。

## 図

- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/beam_hybrid_followup/D10000/c86fc7661da6/analysis/plots/hybrid_win_rate_vs_alpha_beta.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/beam_hybrid_followup/D10000/c86fc7661da6/analysis/plots/hybrid_mean_decision_time.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/beam_hybrid_followup/D10000/c86fc7661da6/analysis/plots/hybrid_mean_effective_depth.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/beam_hybrid_followup/D10000/c86fc7661da6/analysis/plots/hybrid_timeout_rate.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/beam_hybrid_followup/D10000/c86fc7661da6/analysis/plots/hybrid_mean_nodes.png`
- `/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/beam_hybrid_followup/D10000/c86fc7661da6/analysis/plots/hybrid_win_rate_by_dictionary_seed.png`
