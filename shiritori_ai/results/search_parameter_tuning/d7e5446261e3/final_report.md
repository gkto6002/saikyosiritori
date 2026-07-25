# AlphaBeta・PVS・Beamパラメータ調整と適応深度検証

## 1. 実験目的

固定深度の基本設定を先に選び、その後に適応深度の有無と閾値を分離して比較した。HybridAgentは実装していない。

## 2. 既存実装の確認

AI対AIはEdgeDictionaryとAIEdgeStateだけを使う。AlphaBetaのルートalpha共有、PVSのnull window、Beamの候補制限、共通評価関数は維持した。

## 3. ベースライン

- AlphaBeta D5/B8 固定
- PVS D5/B8 固定
- Beam D5/8-6-4-2 固定
- 1手制限 1.0秒

## 4. 実験方法

seed 0・1だけで設定を選び、seed 2は選定後の固定局面と対局確認に用いた。固定局面で安全性を確認してから対局へ進めた。

## 5. 固定局面の作成方法

実対局ログから15局面を抽出した。序盤・中盤・終盤、合法辺数最大・最小、候補評価差最小、枝刈り回数最大、記録時間最大を候補にし、同一turnは重複除去した。

## 6. パラメータ探索範囲

AlphaBeta/PVSはdepth 5・6・7とbranch 8・12・16、Beamは指定4幅とdepth 5・6・7を候補にした。

## 7. 設定の除外基準

深度6のtimeout率20%以下、p95が制限の90%以下、平均ルート完了率50%以上の場合だけ対応する深度7を実行した。
除外された深度7設定は10件だった。

## 8. 固定深度の結果

| agent | config | mean s | p95 s | timeout | nodes | root complete | AB move agreement |
|---|---|---:|---:|---:|---:|---:|---:|
| alpha_beta | alpha_beta_d5_b12 | 0.2450 | 0.8906 | 0.0% | 1945.7 | 100.0% | 100.0% |
| alpha_beta | alpha_beta_d5_b16 | 0.3189 | 1.0000 | 10.0% | 2664.6 | 95.6% | 100.0% |
| alpha_beta | alpha_beta_d5_b8 | 0.0767 | 0.3151 | 0.0% | 1109.8 | 100.0% | 100.0% |
| alpha_beta | alpha_beta_d6_b12 | 0.7696 | 1.0008 | 60.0% | 2962.7 | 60.8% | 100.0% |
| alpha_beta | alpha_beta_d6_b16 | 0.8266 | 1.0005 | 70.0% | 2885.8 | 41.9% | 100.0% |
| alpha_beta | alpha_beta_d6_b8 | 0.3259 | 1.0007 | 10.0% | 2185.1 | 92.5% | 100.0% |
| beam_negamax | beam_negamax_d5_w12-8-4-2 | 0.3433 | 0.8123 | 0.0% | 1365.9 | 100.0% | 60.0% |
| beam_negamax | beam_negamax_d5_w12-8-6-4 | 0.7097 | 1.0003 | 60.0% | 3113.5 | 70.8% | 70.0% |
| beam_negamax | beam_negamax_d5_w16-12-8-4 | 0.8356 | 1.0003 | 60.0% | 3414.1 | 53.8% | 60.0% |
| beam_negamax | beam_negamax_d5_w8-6-4-2 | 0.1749 | 0.4291 | 0.0% | 738.3 | 100.0% | 60.0% |
| beam_negamax | beam_negamax_d6_w12-8-4-2 | 0.5710 | 1.0002 | 20.0% | 2348.8 | 92.5% | 50.0% |
| beam_negamax | beam_negamax_d6_w12-8-6-4 | 0.9468 | 1.0005 | 80.0% | 3295.5 | 34.2% | 60.0% |
| beam_negamax | beam_negamax_d6_w16-12-8-4 | 1.0002 | 1.0006 | 100.0% | 3995.8 | 12.7% | 80.0% |
| beam_negamax | beam_negamax_d6_w8-6-4-2 | 0.4093 | 1.0024 | 10.0% | 1389.5 | 97.5% | 50.0% |
| pvs | pvs_d5_b12 | 0.4440 | 1.0001 | 10.0% | 1728.8 | 91.7% | 90.0% |
| pvs | pvs_d5_b16 | 0.5311 | 1.0001 | 30.0% | 1961.0 | 82.5% | 70.0% |
| pvs | pvs_d5_b8 | 0.2834 | 1.0002 | 10.0% | 1179.9 | 93.8% | 90.0% |
| pvs | pvs_d6_b12 | 0.7321 | 1.0002 | 50.0% | 2792.3 | 63.3% | 100.0% |
| pvs | pvs_d6_b16 | 0.8214 | 1.0011 | 70.0% | 2923.5 | 46.9% | 90.0% |
| pvs | pvs_d6_b8 | 0.5872 | 1.0001 | 10.0% | 2358.9 | 91.2% | 90.0% |

## 9. AlphaBetaの結果

選択設定: `alpha_beta_d5_b8`

## 10. PVSの結果

選択設定: `pvs_d6_b8`

## 11. Beamの結果

選択設定: `beam_negamax_d5_w8-6-4-2`。幅配列を超えるplyでは最後の幅を繰り返す。

## 12. 適応深度の有無の比較

- alpha_beta aggressive: mean=0.2594s, p95=1.0001s, timeout=10.0%, effective depth=4.70
- alpha_beta conservative: mean=0.3448s, p95=1.0001s, timeout=10.0%, effective depth=4.70
- alpha_beta fixed: mean=0.3222s, p95=1.0001s, timeout=10.0%, effective depth=5.00
- alpha_beta standard: mean=0.3062s, p95=1.0003s, timeout=10.0%, effective depth=4.70
- beam_negamax aggressive: mean=0.2452s, p95=0.5138s, timeout=0.0%, effective depth=5.00
- beam_negamax conservative: mean=0.2292s, p95=0.4962s, timeout=0.0%, effective depth=5.00
- beam_negamax fixed: mean=0.2212s, p95=0.5891s, timeout=0.0%, effective depth=5.00
- beam_negamax standard: mean=0.2583s, p95=0.4838s, timeout=0.0%, effective depth=5.00
- pvs aggressive: mean=0.4771s, p95=1.0002s, timeout=40.0%, effective depth=4.80
- pvs conservative: mean=0.4316s, p95=1.0001s, timeout=20.0%, effective depth=4.90
- pvs fixed: mean=0.6742s, p95=1.0455s, timeout=40.0%, effective depth=6.00
- pvs standard: mean=0.4579s, p95=1.0003s, timeout=30.0%, effective depth=5.00

## 13. 適応深度閾値の比較

- alpha_beta: `aggressive`を適応候補として選択
- pvs: `conservative`を適応候補として選択
- beam_negamax: `standard`を適応候補として選択

## 14. 対局実験結果

対局数: 54
- baseline_alpha_beta: 4/6勝 (66.7%), 平均0.2231秒
- baseline_beam_negamax: 3/6勝 (50.0%), 平均0.1768秒
- baseline_pvs: 3/6勝 (50.0%), 平均0.1826秒
- improved_adaptive_alpha_beta: 8/18勝 (44.4%), 平均0.1668秒
- improved_adaptive_beam_negamax: 8/18勝 (44.4%), 平均0.1789秒
- improved_adaptive_pvs: 10/18勝 (55.6%), 平均0.2929秒
- improved_fixed_alpha_beta: 6/12勝 (50.0%), 平均0.2045秒
- improved_fixed_beam_negamax: 6/12勝 (50.0%), 平均0.1832秒
- improved_fixed_pvs: 6/12勝 (50.0%), 平均0.4016秒

## 15. 先手・後手別分析

- first baseline_alpha_beta: 33.3%
- first baseline_beam_negamax: 33.3%
- first baseline_pvs: 33.3%
- first improved_adaptive_alpha_beta: 55.6%
- first improved_adaptive_beam_negamax: 44.4%
- first improved_adaptive_pvs: 55.6%
- first improved_fixed_alpha_beta: 33.3%
- first improved_fixed_beam_negamax: 33.3%
- first improved_fixed_pvs: 33.3%
- second baseline_alpha_beta: 100.0%
- second baseline_beam_negamax: 66.7%
- second baseline_pvs: 66.7%
- second improved_adaptive_alpha_beta: 33.3%
- second improved_adaptive_beam_negamax: 44.4%
- second improved_adaptive_pvs: 55.6%
- second improved_fixed_alpha_beta: 66.7%
- second improved_fixed_beam_negamax: 66.7%
- second improved_fixed_pvs: 66.7%

## 16. 辞書seed別分析

- seed 0 baseline_alpha_beta: 100.0%
- seed 0 baseline_beam_negamax: 50.0%
- seed 0 baseline_pvs: 100.0%
- seed 0 improved_adaptive_alpha_beta: 50.0%
- seed 0 improved_adaptive_beam_negamax: 50.0%
- seed 0 improved_adaptive_pvs: 33.3%
- seed 0 improved_fixed_alpha_beta: 25.0%
- seed 0 improved_fixed_beam_negamax: 50.0%
- seed 0 improved_fixed_pvs: 50.0%
- seed 1 baseline_alpha_beta: 50.0%
- seed 1 baseline_beam_negamax: 50.0%
- seed 1 baseline_pvs: 50.0%
- seed 1 improved_adaptive_alpha_beta: 50.0%
- seed 1 improved_adaptive_beam_negamax: 33.3%
- seed 1 improved_adaptive_pvs: 66.7%
- seed 1 improved_fixed_alpha_beta: 75.0%
- seed 1 improved_fixed_beam_negamax: 50.0%
- seed 1 improved_fixed_pvs: 25.0%
- seed 2 baseline_alpha_beta: 50.0%
- seed 2 baseline_beam_negamax: 50.0%
- seed 2 baseline_pvs: 0.0%
- seed 2 improved_adaptive_alpha_beta: 33.3%
- seed 2 improved_adaptive_beam_negamax: 50.0%
- seed 2 improved_adaptive_pvs: 66.7%
- seed 2 improved_fixed_alpha_beta: 50.0%
- seed 2 improved_fixed_beam_negamax: 50.0%
- seed 2 improved_fixed_pvs: 75.0%

## 17. 処理時間の内訳

合法手生成、候補評価、候補ソート、ルート順序付け、再帰内順序付け、葉評価、再帰その他、その他をログへ保存した。candidate evaluationとsortの合計はordering timeの内訳である。

## 18. 深度変更が選択手へ与えた影響

適応ログには各手のeffective depth、変更前後、変更理由、回復連続回数、残存語数、合法辺数を保存した。詳細は`adaptive/runs.csv`を参照。
- alpha_beta fixed: 深度低下0/10、低下時の手変更率0.0%、上下反転0回
- alpha_beta conservative: 深度低下3/10、低下時の手変更率33.3%、上下反転0回
- alpha_beta standard: 深度低下3/10、低下時の手変更率33.3%、上下反転0回
- alpha_beta aggressive: 深度低下3/10、低下時の手変更率33.3%、上下反転1回
- pvs fixed: 深度低下0/10、低下時の手変更率0.0%、上下反転0回
- pvs conservative: 深度低下8/10、低下時の手変更率37.5%、上下反転0回
- pvs standard: 深度低下7/10、低下時の手変更率28.6%、上下反転0回
- pvs aggressive: 深度低下7/10、低下時の手変更率14.3%、上下反転1回
- beam_negamax fixed: 深度低下0/10、低下時の手変更率0.0%、上下反転0回
- beam_negamax conservative: 深度低下0/10、低下時の手変更率0.0%、上下反転0回
- beam_negamax standard: 深度低下0/10、低下時の手変更率0.0%、上下反転0回
- beam_negamax aggressive: 深度低下0/10、低下時の手変更率0.0%、上下反転0回

## 19. AlphaBetaより他手法が速くならない理由

PVSはnull-windowのノード削減が再探索と候補順序評価のコストで相殺される局面がある。Beamは枝刈りを使わず、残した候補を均等に読むため、幅を絞ってもAlphaBetaより多くのノードを読む場合がある。局面別散布図を併記した。

## 20. 各手法の強みと弱み

- AlphaBeta: ルートalpha共有と良い候補順序で安定。
- PVS: 順序が当たれば少ノードだが再探索コストがある。
- Beam: 計算量を幅で制御できるが参照手を落とす近似誤差がある。

## 21. 採用すべき最終設定

- alpha_beta: 固定 `alpha_beta_d5_b8`、適応候補 `aggressive`
- pvs: 固定 `pvs_d6_b8`、適応候補 `conservative`
- beam_negamax: 固定 `beam_negamax_d5_w8-6-4-2`、適応候補 `standard`

## 22. 採用しなかった設定と理由

- alpha_beta_d7_b8: corresponding depth-6 setting failed safety gate: timeout=0.100, p95=1.001, root_completion=0.925
- alpha_beta_d7_b12: corresponding depth-6 setting failed safety gate: timeout=0.600, p95=1.001, root_completion=0.608
- alpha_beta_d7_b16: corresponding depth-6 setting failed safety gate: timeout=0.700, p95=1.001, root_completion=0.419
- pvs_d7_b8: corresponding depth-6 setting failed safety gate: timeout=0.100, p95=1.000, root_completion=0.912
- pvs_d7_b12: corresponding depth-6 setting failed safety gate: timeout=0.500, p95=1.000, root_completion=0.633
- pvs_d7_b16: corresponding depth-6 setting failed safety gate: timeout=0.700, p95=1.001, root_completion=0.469
- beam_negamax_d7_w8-6-4-2: corresponding depth-6 setting failed safety gate: timeout=0.100, p95=1.002, root_completion=0.975
- beam_negamax_d7_w12-8-4-2: corresponding depth-6 setting failed safety gate: timeout=0.200, p95=1.000, root_completion=0.925
- beam_negamax_d7_w12-8-6-4: corresponding depth-6 setting failed safety gate: timeout=0.800, p95=1.000, root_completion=0.342
- beam_negamax_d7_w16-12-8-4: corresponding depth-6 setting failed safety gate: timeout=1.000, p95=1.001, root_completion=0.127

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
- source fingerprint: `85693e84c50e1f825804f493548085ff7855504dd431ae0a4f399de35e61487f`
- plots: 17

## 制限と簡略化

AlphaBetaは参照手であり真の最善手ではない。Beam内部の各plyで参照主変化を追跡せず、ルート保持率を測った。固定局面は実ログ依存で、すべての局面型を完全には網羅しない。
