# AlphaBeta・PVS・Beamパラメータ調整と適応深度検証

## 1. 実験目的

固定深度の基本設定を先に選び、その後に適応深度の有無と閾値を分離して比較した。HybridAgentは実装していない。

## 2. 既存実装の確認

AI対AIはEdgeDictionaryとAIEdgeStateだけを使う。AlphaBetaのルートalpha共有、PVSのnull window、Beamの候補制限、共通評価関数は維持した。

## 3. ベースライン

- AlphaBeta D5/B8 固定
- PVS D5/B8 固定
- Beam D5/8-6-4-2 固定
- 1手制限 0.15秒

## 4. 実験方法

seed 0・1だけで設定を選び、seed 2は選定後の固定局面と対局確認に用いた。固定局面で安全性を確認してから対局へ進めた。

## 5. 固定局面の作成方法

実対局ログから9局面を抽出した。序盤・中盤・終盤、合法辺数最大・最小、候補評価差最小、枝刈り回数最大、記録時間最大を候補にし、同一turnは重複除去した。

## 6. パラメータ探索範囲

AlphaBeta/PVSはdepth 5・6・7とbranch 8・12・16、Beamは指定4幅とdepth 5・6・7を候補にした。

## 7. 設定の除外基準

深度6のtimeout率20%以下、p95が制限の90%以下、平均ルート完了率50%以上の場合だけ対応する深度7を実行した。
除外された深度7設定は10件だった。

## 8. 固定深度の結果

| agent | config | mean s | p95 s | timeout | nodes | root complete | AB move agreement |
|---|---|---:|---:|---:|---:|---:|---:|
| alpha_beta | alpha_beta_d5_b12 | 0.1145 | 0.1502 | 66.7% | 435.5 | 50.0% | 100.0% |
| alpha_beta | alpha_beta_d5_b16 | 0.1242 | 0.1502 | 66.7% | 441.0 | 38.5% | 100.0% |
| alpha_beta | alpha_beta_d5_b8 | 0.0964 | 0.1502 | 50.0% | 403.7 | 72.9% | 100.0% |
| alpha_beta | alpha_beta_d6_b12 | 0.1307 | 0.1522 | 83.3% | 452.8 | 25.0% | 100.0% |
| alpha_beta | alpha_beta_d6_b16 | 0.1287 | 0.1502 | 83.3% | 395.2 | 25.0% | 100.0% |
| alpha_beta | alpha_beta_d6_b8 | 0.1406 | 0.2209 | 83.3% | 424.5 | 25.0% | 100.0% |
| beam_negamax | beam_negamax_d5_w12-8-4-2 | 0.1164 | 0.1502 | 66.7% | 533.7 | 59.7% | 100.0% |
| beam_negamax | beam_negamax_d5_w12-8-6-4 | 0.1502 | 0.1504 | 100.0% | 622.5 | 23.6% | 100.0% |
| beam_negamax | beam_negamax_d5_w16-12-8-4 | 0.1501 | 0.1502 | 100.0% | 651.0 | 18.1% | 100.0% |
| beam_negamax | beam_negamax_d5_w8-6-4-2 | 0.1159 | 0.1563 | 66.7% | 483.8 | 75.0% | 83.3% |
| beam_negamax | beam_negamax_d6_w12-8-4-2 | 0.1301 | 0.1505 | 66.7% | 507.2 | 44.4% | 83.3% |
| beam_negamax | beam_negamax_d6_w12-8-6-4 | 0.1501 | 0.1502 | 100.0% | 615.7 | 15.3% | 100.0% |
| beam_negamax | beam_negamax_d6_w16-12-8-4 | 0.1502 | 0.1504 | 100.0% | 690.8 | 14.9% | 100.0% |
| beam_negamax | beam_negamax_d6_w8-6-4-2 | 0.1214 | 0.1505 | 66.7% | 577.5 | 58.3% | 83.3% |
| pvs | pvs_d5_b12 | 0.1179 | 0.1502 | 66.7% | 404.7 | 44.4% | 100.0% |
| pvs | pvs_d5_b16 | 0.1296 | 0.1515 | 66.7% | 413.0 | 39.6% | 100.0% |
| pvs | pvs_d5_b8 | 0.1022 | 0.1501 | 50.0% | 428.5 | 72.9% | 83.3% |
| pvs | pvs_d6_b12 | 0.1280 | 0.1520 | 83.3% | 491.5 | 25.0% | 100.0% |
| pvs | pvs_d6_b16 | 0.1291 | 0.1508 | 83.3% | 488.7 | 25.0% | 100.0% |
| pvs | pvs_d6_b8 | 0.1297 | 0.1697 | 83.3% | 457.5 | 16.7% | 100.0% |

## 9. AlphaBetaの結果

選択設定: `alpha_beta_d6_b16`

## 10. PVSの結果

選択設定: `pvs_d6_b16`

## 11. Beamの結果

選択設定: `beam_negamax_d6_w12-8-6-4`。幅配列を超えるplyでは最後の幅を繰り返す。

## 12. 適応深度の有無の比較

- alpha_beta aggressive: mean=0.1284s, p95=0.1544s, timeout=83.3%, effective depth=5.00
- alpha_beta conservative: mean=0.1245s, p95=0.1503s, timeout=66.7%, effective depth=5.00
- alpha_beta fixed: mean=0.1321s, p95=0.1508s, timeout=83.3%, effective depth=6.00
- alpha_beta standard: mean=0.1219s, p95=0.1517s, timeout=66.7%, effective depth=5.17
- beam_negamax aggressive: mean=0.1397s, p95=0.1505s, timeout=83.3%, effective depth=5.00
- beam_negamax conservative: mean=0.1390s, p95=0.1502s, timeout=83.3%, effective depth=5.00
- beam_negamax fixed: mean=0.1502s, p95=0.1503s, timeout=100.0%, effective depth=6.00
- beam_negamax standard: mean=0.1385s, p95=0.1502s, timeout=83.3%, effective depth=5.00
- pvs aggressive: mean=0.1247s, p95=0.1502s, timeout=66.7%, effective depth=5.17
- pvs conservative: mean=0.1187s, p95=0.1502s, timeout=66.7%, effective depth=5.17
- pvs fixed: mean=0.1323s, p95=0.1582s, timeout=83.3%, effective depth=6.00
- pvs standard: mean=0.1260s, p95=0.1775s, timeout=66.7%, effective depth=5.17

## 13. 適応深度閾値の比較

- alpha_beta: `standard`を適応候補として選択
- pvs: `conservative`を適応候補として選択
- beam_negamax: `standard`を適応候補として選択

## 14. 対局実験結果

対局数: 16
- baseline_alpha_beta: 0/2勝 (0.0%), 平均0.1122秒
- baseline_beam_negamax: 2/2勝 (100.0%), 平均0.1504秒
- baseline_pvs: 2/3勝 (66.7%), 平均0.1082秒
- improved_adaptive_alpha_beta: 6/7勝 (85.7%), 平均0.1194秒
- improved_adaptive_beam_negamax: 3/8勝 (37.5%), 平均0.1433秒
- improved_adaptive_pvs: 3/10勝 (30.0%), 平均0.1238秒

## 15. 先手・後手別分析

- first baseline_alpha_beta: 0.0%
- first baseline_beam_negamax: 100.0%
- first baseline_pvs: 0.0%
- first improved_adaptive_alpha_beta: 66.7%
- first improved_adaptive_beam_negamax: 0.0%
- first improved_adaptive_pvs: 0.0%
- second baseline_alpha_beta: 0.0%
- second baseline_beam_negamax: 100.0%
- second baseline_pvs: 100.0%
- second improved_adaptive_alpha_beta: 100.0%
- second improved_adaptive_beam_negamax: 75.0%
- second improved_adaptive_pvs: 75.0%

## 16. 辞書seed別分析

- seed 0 baseline_alpha_beta: 0.0%
- seed 0 baseline_beam_negamax: 100.0%
- seed 0 baseline_pvs: 66.7%
- seed 0 improved_adaptive_alpha_beta: 85.7%
- seed 0 improved_adaptive_beam_negamax: 37.5%
- seed 0 improved_adaptive_pvs: 30.0%

## 17. 処理時間の内訳

合法手生成、候補評価、候補ソート、ルート順序付け、再帰内順序付け、葉評価、再帰その他、その他をログへ保存した。candidate evaluationとsortの合計はordering timeの内訳である。

## 18. 深度変更が選択手へ与えた影響

適応ログには各手のeffective depth、変更前後、変更理由、回復連続回数、残存語数、合法辺数を保存した。詳細は`adaptive/runs.csv`を参照。

## 19. AlphaBetaより他手法が速くならない理由

PVSはnull-windowのノード削減が再探索と候補順序評価のコストで相殺される局面がある。Beamは枝刈りを使わず、残した候補を均等に読むため、幅を絞ってもAlphaBetaより多くのノードを読む場合がある。局面別散布図を併記した。

## 20. 各手法の強みと弱み

- AlphaBeta: ルートalpha共有と良い候補順序で安定。
- PVS: 順序が当たれば少ノードだが再探索コストがある。
- Beam: 計算量を幅で制御できるが参照手を落とす近似誤差がある。

## 21. 採用すべき最終設定

- alpha_beta: 固定 `alpha_beta_d6_b16`、適応候補 `standard`
- pvs: 固定 `pvs_d6_b16`、適応候補 `conservative`
- beam_negamax: 固定 `beam_negamax_d6_w12-8-6-4`、適応候補 `standard`

## 22. 採用しなかった設定と理由

- alpha_beta_d7_b8: corresponding depth-6 setting failed safety gate: timeout=0.833, p95=0.221, root_completion=0.250
- alpha_beta_d7_b12: corresponding depth-6 setting failed safety gate: timeout=0.833, p95=0.152, root_completion=0.250
- alpha_beta_d7_b16: corresponding depth-6 setting failed safety gate: timeout=0.833, p95=0.150, root_completion=0.250
- pvs_d7_b8: corresponding depth-6 setting failed safety gate: timeout=0.833, p95=0.170, root_completion=0.167
- pvs_d7_b12: corresponding depth-6 setting failed safety gate: timeout=0.833, p95=0.152, root_completion=0.250
- pvs_d7_b16: corresponding depth-6 setting failed safety gate: timeout=0.833, p95=0.151, root_completion=0.250
- beam_negamax_d7_w8-6-4-2: corresponding depth-6 setting failed safety gate: timeout=0.667, p95=0.151, root_completion=0.583
- beam_negamax_d7_w12-8-4-2: corresponding depth-6 setting failed safety gate: timeout=0.667, p95=0.151, root_completion=0.444
- beam_negamax_d7_w12-8-6-4: corresponding depth-6 setting failed safety gate: timeout=1.000, p95=0.150, root_completion=0.153
- beam_negamax_d7_w16-12-8-4: corresponding depth-6 setting failed safety gate: timeout=1.000, p95=0.150, root_completion=0.149

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
- source fingerprint: `e5c0fd6ec1f616b881d6bfe5dee024cc38cd5de6ca5e580784a5c8764dd496ed`
- plots: 17

## 制限と簡略化

AlphaBetaは参照手であり真の最善手ではない。Beam内部の各plyで参照主変化を追跡せず、ルート保持率を測った。固定局面は実ログ依存で、すべての局面型を完全には網羅しない。
