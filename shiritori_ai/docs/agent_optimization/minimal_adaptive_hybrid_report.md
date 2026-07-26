# D10000 最小盤面適応ハイブリッド実験

## 結論

今回の D10000 保存局面比較では、候補評価差型
`ScoreGapDynamicBeamAlphaBetaAgent` と選択候補限定型
`SelectiveProofAlphaBetaAgent` のどちらにも、固定
`BeamAlphaBetaAgent` を置き換える優位性は確認できなかった。
事前に定めた採用基準に従い、短い対局と両機構の統合型は省略した。
現時点の採用方式は固定 BeamAlphaBeta のままとする。

## GitHub と既存結果の確認

- GitHub `main` とローカル `main` は作業開始時点で
  `2880aa84efce7c86e650b4baa155915dda225c9d` と一致していた。
- D10000 の既存保存局面 14 件と、
  `results/position_adaptive_hybrid_v2/tune/D10000/07a64484d43c/raw_matches.jsonl`
  を再利用した。
- 既存 v2 実験では ProofExtension の完全解析試行が非常に多い一方、
  D10000 の探索葉は到達部分が大きく、実用的な厳密解析へ切り替わりにくい
  傾向が確認されていた。

## 実装

### 候補評価差型 DynamicBeamAlphaBeta

- 既存の手順序付けで計算済みの `CandidateEvaluation.total_score` を再利用する。
- 上位二候補の評価差が小さいと深さ別最大幅、大きいと最小幅、
  中間なら固定 Beam 幅を使用する。
- root だけでなく再帰中の全 ply へ同じフックを適用する。
- 候補数、選択数、除外数、幅、上位評価差を ply 別に集計する。
- 前回選択した root 手が同じ候補集合に残っている場合は Beam 外へ落とさない。
  既存 BeamAlphaBeta は内部反復深化を行わないため、
  「前回反復」のためだけの新しい反復深化は追加していない。

評価した二設定は次のとおり。

| 設定 | 評価差の広幅閾値 | 狭幅閾値 | 最小幅 | 最大幅 |
|---|---:|---:|---|---|
| conservative | 3 | 16 | 8,6,3,2 | 16,10,5,2 |
| responsive | 6 | 12 | 6,4,2,1 | 18,12,6,3 |

### SelectiveProofAlphaBeta

- 最初に通常の固定 BeamAlphaBeta を実行する。
- root 探索スコアの上位二候補に加え、評価差が小さい候補を含めて最大三候補に絞る。
- 候補を一手適用した残余グラフが閾値内の場合だけ既存
  `ShiritoriSolver` で解析する。
- 一手の完全解析予算は総時間の 15% または 20%、呼出しは最大三回とした。
- 完了した解析だけを利用する。中断・不適格時は通常探索手を完全に維持する。
- 厳密勝ち、未確定、厳密負けの順で通常評価より優先する。
- 呼出し位置、候補、ply、到達語数、辺種類数、頂点数、状態数、時間、
  完了状態、結果、通常評価との差を記録する。

strict は到達語数 18、辺種類 12、頂点 10、状態推定 50,000、
時間 15% を上限とした。moderate は順に 28、18、12、100,000、
時間 20% とした。

## 完全解析正解データ

既存 D10000 対局ログから合法辺が二種類以上ある終盤局面を 510 件抽出し、
特に合法辺が少ない 30 件へ一局面 0.3 秒の完全解析を試した。
完了した局面は 0 件だった。

最も対局が進んだ局面でも 452 手時点で、要求文字から到達可能な未使用語は
約 9,476 語、辺種類は約 1,990、文字頂点は 67 残っていた。
D10000 の通常対局は語彙を使い切る前に「ん」または合法手なしで終了するため、
見かけ上の終盤でも未使用グラフの強連結部分が大きいことが原因である。
時間上限または状態上限を超えた結果は正解データへ採用していない。

したがって今回の正解率は、50 保存局面中、1 秒の深い参照探索が安定完了した
49 局面を分母とする。厳密解と参照探索を混ぜて厳密解のように扱ってはいない。

## 保存局面比較

比較条件は D10000、50 局面、固定深度 8、一手 0.3 秒。
参照は固定 Beam 幅の深度 10、一手 1 秒とした。

| 方式 | 参照手一致率 | 平均時間 | 平均ノード | 深度 | 内部時間切れ | 手変更 | 改善 | 悪化 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 固定 BeamAlphaBeta | 69.4% | 0.1214 s | 1,670 | 8.00 | 6.0% | 0 | 0 | 0 |
| gap conservative | 44.9% | 0.0804 s | 1,102 | 8.00 | 0.0% | 25 | 4 | 16 |
| gap responsive | 55.1% | 0.0122 s | 182 | 8.00 | 0.0% | 26 | 6 | 13 |
| proof strict | 69.4% | 0.1196 s | 1,639 | 8.00 | 4.0% | 0 | 0 | 0 |
| proof moderate | 69.4% | 0.1200 s | 1,628 | 8.00 | 8.0% | 0 | 0 | 0 |

候補評価差型は conservative で時間を約 34%、ノードを約 34%削減し、
responsive では時間を約 90%、ノードを約 89%削減した。しかし一致率低下が
それぞれ 24.5 ポイント、14.3 ポイントあり、速度向上と引き換えの精度低下が
大きすぎる。

SelectiveProof の完全解析完了は strict 5 件、moderate 6 件だったが、
すべて「ん」終端を直接判定した自明な結果だった。非自明成功、完全解析による
選択変更、改善、悪化はいずれも 0 件である。

## 採否

- 候補評価差型: 不採用。10%以上の削減条件は満たすが、一致率を維持できない。
- SelectiveProof: 不採用。通常探索への悪影響は小さいが、非自明成功と改善がない。
- DynamicSelectiveProof: 未実装。単体二方式がともに採用基準を通らなかったため。
- 固定 BeamAlphaBeta: 継続採用。

事前基準を通過した方式がないため、5 seed・先後入替の短い対局は実行していない。
これは失敗を隠した省略ではなく、効果のない方式へ対局時間を使わないために
最初から定めた段階停止条件による。

## 変更ファイル

- `src/search_common.py`
- `src/agents.py`
- `src/adaptive_hybrid.py`
- `src/run_position_adaptive_hybrid_experiment.py`
- `src/run_minimal_adaptive_hybrid_experiment.py`
- `tests/test_adaptive_hybrid.py`
- `.gitignore`

固定 BeamAlphaBeta の候補制限と選択規則は変更していない。共通変更は、
候補順序フックへ既に計算済みの評価辞書を渡すこと、root の完了済み探索スコアを
ログへ残すこと、評価差統計を `SearchStats` へ追加することに限定した。

## テスト

新たに次を検証した。

- 評価差幅が再帰 ply でも適用される。
- 選択候補数が決定幅を超えない。
- 前回の root 最善手が除外されない。
- 固定 Beam に評価差ポリシーが混入しない。
- 完全解析完了時だけ厳密値を使う。
- 完全解析中断時は通常探索結果を維持する。
- 複数候補の既知小局面で厳密な勝ち手を選ぶ。
- 新方式が合法手を返し、状態を変更せず、同一 seed で再現する。

全テストの最終結果は 217 件成功、0 件失敗。

## 出力

`results/minimal_adaptive_hybrid/D10000/` に次を生成した。

- `benchmark_summary.json`, `benchmark_summary.csv`
- `dynamic_beam_width_events.csv`
- `selective_proof_events.csv`
- `reference_match_rate.png`
- `mean_decision_time.png`
- `mean_nodes.png`
- `report.md`

棒グラフには値ラベルを表示する。再生用の生局面と各局面の詳細 JSON Lines は
Git へ含めず、`.gitignore` の対象とした。

## 実行コマンド

```bash
.venv/bin/python -m unittest discover -s tests -v

.venv/bin/python -u src/run_minimal_adaptive_hybrid_experiment.py \
  --stage prepare \
  --truth-time-sec 0.3 \
  --confirm-d10000

.venv/bin/python -u src/run_minimal_adaptive_hybrid_experiment.py \
  --stage benchmark \
  --confirm-d10000

.venv/bin/python -u src/run_minimal_adaptive_hybrid_experiment.py \
  --stage matches \
  --confirm-d10000

.venv/bin/python -u src/run_minimal_adaptive_hybrid_experiment.py \
  --stage analyze \
  --confirm-d10000
```

一括再実行する場合は次を使用する。

```bash
.venv/bin/python -u src/run_minimal_adaptive_hybrid_experiment.py \
  --stage all \
  --truth-time-sec 0.3 \
  --confirm-d10000 \
  --output results/minimal_adaptive_hybrid/D10000_rerun
```

## 次に試すなら

評価差だけで幅を狭める方式では、簡易評価の誤差をそのまま探索漏れへ変換して
しまう。次に強化するなら、評価差を幅の決定ではなく「探索順序」や
浅い確認探索の割当てへ使い、固定幅を維持する方が安全である。

完全解析は D10000 の通常状態へ直接組み込むのではなく、強連結成分の縮約や
勝敗に無関係な辺の安全な除去によって、完全解析器へ渡す残余ゲームそのものを
小さくできる場合にだけ再検討する価値がある。
