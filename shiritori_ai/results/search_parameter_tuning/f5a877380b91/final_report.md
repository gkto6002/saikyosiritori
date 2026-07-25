# AlphaBeta・PVS・Beamパラメータ調整と適応深度検証

## 1. 実験目的

D10000で固定設定と適応深度を比較した。固定設定は`/Users/onumagakuto/Documents/最強しりとり/shiritori_ai/results/search_parameter_tuning/f2d5471f97bd`から移植して再検証した。HybridAgentは実装していない。

## 2. 既存実装の確認

AI対AIはEdgeDictionaryとAIEdgeStateだけを使う。AlphaBetaのルートalpha共有、PVSのnull window、Beamの候補制限、共通評価関数は維持した。

## 3. ベースライン

- AlphaBeta D5/B8 固定
- PVS D5/B8 固定
- Beam D5/8-6-4-2 固定
- 1手制限 1.0秒

## 4. 実験方法

D10000のseed 0・1で設定を選び、seed 2は選定後の固定局面と対局確認に用いた。固定局面で安全性を確認してから対局へ進めた。

## 5. 固定局面の作成方法

実対局ログから14局面を抽出した。序盤・中盤・終盤、合法辺数最大・最小、候補評価差最小、枝刈り回数最大、記録時間最大を候補にし、同一turnは重複除去した。

## 6. パラメータ探索範囲

移植元で選定済みのAlphaBeta、PVS、BeamNegamax各1設定を固定深度で再検証した。

## 7. 設定の除外基準

深度6のtimeout率20%以下、p95が制限の90%以下、平均ルート完了率50%以上の場合だけ対応する深度7を実行した。
除外された深度7設定は0件だった。

## 8. 固定深度の結果

| agent | config | mean s | p95 s | timeout | nodes | root complete | AB move agreement |
|---|---|---:|---:|---:|---:|---:|---:|
| alpha_beta | alpha_beta_d5_b8 | 0.1880 | 0.3197 | 0.0% | 2065.4 | 100.0% | 0.0% |
| beam_negamax | beam_negamax_d6_w8-6-4-2 | 0.1694 | 0.1798 | 0.0% | 2895.2 | 100.0% | 0.0% |
| pvs | pvs_d5_b8 | 0.1406 | 0.2240 | 0.0% | 1720.1 | 100.0% | 0.0% |

## 9. AlphaBetaの結果

選択設定: `alpha_beta_d5_b8`

## 10. PVSの結果

選択設定: `pvs_d5_b8`

## 11. Beamの結果

選択設定: `beam_negamax_d6_w8-6-4-2`。幅配列を超えるplyでは最後の幅を繰り返す。

## 12. 適応深度の有無の比較

- alpha_beta aggressive: mean=0.2824s, p95=0.6172s, timeout=0.0%, effective depth=5.33
- alpha_beta conservative: mean=0.1078s, p95=0.2481s, timeout=0.0%, effective depth=4.33
- alpha_beta fixed: mean=0.1891s, p95=0.2960s, timeout=0.0%, effective depth=5.00
- alpha_beta standard: mean=0.2884s, p95=0.9925s, timeout=0.0%, effective depth=5.22
- beam_negamax aggressive: mean=0.2820s, p95=0.4546s, timeout=0.0%, effective depth=6.56
- beam_negamax conservative: mean=0.1717s, p95=0.1835s, timeout=0.0%, effective depth=6.00
- beam_negamax fixed: mean=0.1789s, p95=0.2384s, timeout=0.0%, effective depth=6.00
- beam_negamax standard: mean=0.2357s, p95=0.4055s, timeout=0.0%, effective depth=6.33
- pvs aggressive: mean=0.2921s, p95=0.5285s, timeout=0.0%, effective depth=5.56
- pvs conservative: mean=0.1252s, p95=0.2162s, timeout=0.0%, effective depth=4.78
- pvs fixed: mean=0.1463s, p95=0.2215s, timeout=0.0%, effective depth=5.00
- pvs standard: mean=0.1909s, p95=0.5337s, timeout=0.0%, effective depth=5.11

## 13. 適応深度閾値の比較

- alpha_beta: `aggressive`を適応候補として選択
- pvs: `aggressive`を適応候補として選択
- beam_negamax: `aggressive`を適応候補として選択

## 14. 対局実験結果

対局数: 36
- improved_adaptive_alpha_beta: 11/18勝 (61.1%), 平均0.3429秒
- improved_adaptive_beam_negamax: 7/18勝 (38.9%), 平均0.3897秒
- improved_adaptive_pvs: 11/18勝 (61.1%), 平均0.3284秒
- improved_fixed_alpha_beta: 2/6勝 (33.3%), 平均0.1184秒
- improved_fixed_beam_negamax: 2/6勝 (33.3%), 平均0.1909秒
- improved_fixed_pvs: 3/6勝 (50.0%), 平均0.1202秒

## 15. 先手・後手別分析

- first improved_adaptive_alpha_beta: 44.4%
- first improved_adaptive_beam_negamax: 33.3%
- first improved_adaptive_pvs: 44.4%
- first improved_fixed_alpha_beta: 33.3%
- first improved_fixed_beam_negamax: 33.3%
- first improved_fixed_pvs: 33.3%
- second improved_adaptive_alpha_beta: 77.8%
- second improved_adaptive_beam_negamax: 44.4%
- second improved_adaptive_pvs: 77.8%
- second improved_fixed_alpha_beta: 33.3%
- second improved_fixed_beam_negamax: 33.3%
- second improved_fixed_pvs: 66.7%

## 16. 辞書seed別分析

- seed 0 improved_adaptive_alpha_beta: 66.7%
- seed 0 improved_adaptive_beam_negamax: 16.7%
- seed 0 improved_adaptive_pvs: 83.3%
- seed 0 improved_fixed_alpha_beta: 0.0%
- seed 0 improved_fixed_beam_negamax: 50.0%
- seed 0 improved_fixed_pvs: 50.0%
- seed 1 improved_adaptive_alpha_beta: 66.7%
- seed 1 improved_adaptive_beam_negamax: 66.7%
- seed 1 improved_adaptive_pvs: 66.7%
- seed 1 improved_fixed_alpha_beta: 0.0%
- seed 1 improved_fixed_beam_negamax: 0.0%
- seed 1 improved_fixed_pvs: 0.0%
- seed 2 improved_adaptive_alpha_beta: 50.0%
- seed 2 improved_adaptive_beam_negamax: 33.3%
- seed 2 improved_adaptive_pvs: 33.3%
- seed 2 improved_fixed_alpha_beta: 100.0%
- seed 2 improved_fixed_beam_negamax: 50.0%
- seed 2 improved_fixed_pvs: 100.0%

## 17. 処理時間の内訳

合法手生成、候補評価、候補ソート、ルート順序付け、再帰内順序付け、葉評価、再帰その他、その他をログへ保存した。candidate evaluationとsortの合計はordering timeの内訳である。

## 18. 深度変更が選択手へ与えた影響

適応ログには各手のeffective depth、変更前後、変更理由、回復連続回数、残存語数、合法辺数を保存した。詳細は`adaptive/runs.csv`を参照。
- alpha_beta fixed: 深度低下0/9、低下時の手変更率0.0%、上下反転0回
- alpha_beta conservative: 深度低下6/9、低下時の手変更率50.0%、上下反転3回
- alpha_beta standard: 深度低下0/9、低下時の手変更率0.0%、上下反転1回
- alpha_beta aggressive: 深度低下0/9、低下時の手変更率0.0%、上下反転2回
- pvs fixed: 深度低下0/9、低下時の手変更率0.0%、上下反転0回
- pvs conservative: 深度低下2/9、低下時の手変更率50.0%、上下反転0回
- pvs standard: 深度低下0/9、低下時の手変更率0.0%、上下反転1回
- pvs aggressive: 深度低下0/9、低下時の手変更率0.0%、上下反転0回
- beam_negamax fixed: 深度低下0/9、低下時の手変更率0.0%、上下反転0回
- beam_negamax conservative: 深度低下0/9、低下時の手変更率0.0%、上下反転0回
- beam_negamax standard: 深度低下0/9、低下時の手変更率0.0%、上下反転1回
- beam_negamax aggressive: 深度低下0/9、低下時の手変更率0.0%、上下反転0回

## 19. AlphaBetaより他手法が速くならない理由

PVSはnull-windowのノード削減が再探索と候補順序評価のコストで相殺される局面がある。Beamは枝刈りを使わず、残した候補を均等に読むため、幅を絞ってもAlphaBetaより多くのノードを読む場合がある。局面別散布図を併記した。

## 20. 各手法の強みと弱み

- AlphaBeta: ルートalpha共有と良い候補順序で安定。
- PVS: 順序が当たれば少ノードだが再探索コストがある。
- Beam: 計算量を幅で制御できるが参照手を落とす近似誤差がある。

## 21. 採用すべき最終設定

- alpha_beta: 固定 `alpha_beta_d5_b8`、適応候補 `aggressive`
- pvs: 固定 `pvs_d5_b8`、適応候補 `aggressive`
- beam_negamax: 固定 `beam_negamax_d6_w8-6-4-2`、適応候補 `aggressive`

## 22. 採用しなかった設定と理由


## 23. HybridAgentへ利用できそうな知見

合法辺数、残存語数、固定深度の実測時間、AlphaBeta参照手のBeam順位は、将来の方式切替や深度選択に使える。今回は切替ロジックを実装していない。

## 24. 今後の改善案

前手時間だけでなく現在局面の合法辺数と残存語数を使う深度予測、候補順序改善、置換表を個別に検証する。

## 25. 反復深化を導入する価値の評価

現在方式は単一深度を途中まで読むため、timeout時に完了済み浅い探索結果を保証しない。反復深化は安全な完成手を保持し、次反復の手順序にも利用できるため価値が高い。ただし今回の範囲外である。

## 26. 再現手順

```bash
.venv/bin/python src/run_search_parameter_tuning.py --full
```

- commit: `aa9f58450ba3718b762c520414b6ddb33489d464`
- source fingerprint: `6d3d9a70d358c1c5b2f9ff4ce72a1aa71874bb235ccb44c50843d188b214e39c`
- plots: 17

## 制限と簡略化

AlphaBetaは参照手であり真の最善手ではない。Beam内部の各plyで参照主変化を追跡せず、ルート保持率を測った。固定局面は実ログ依存で、すべての局面型を完全には網羅しない。
