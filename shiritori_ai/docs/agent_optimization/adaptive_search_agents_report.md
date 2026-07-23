# 適応探索AI・共通評価実装レポート

> この文書は初回実装時点の記録である。現在の軽量順序評価、差分集計、標準深度・候補上限、ソフトタイムアウトは`edge_native_search_performance_report.md`を参照。

## 目的

`RuntimeDictionary`、`EdgeDictionary`、`AIEdgeState`を使うAI対AIを主経路とし、タイムアウトの正しい伝播、共通の適応深度、攻撃・生存評価、Beam Negamax、Aggressive PVSを実装する。WordGraphの`choose_move`は互換用に維持する。

## 変更ファイル

- `src/search_common.py`: 共通評価、`SearchTimeout`、探索統計、適応深度
- `src/agents.py`: 既存AIの修正、BeamNegamax、AggressivePVS、MonteCarloラウンドロビン
- `src/match.py`: 探索統計の対局ログ接続
- `src/experiments_approx.py`: 新AIと設定CLI、CSV列
- `src/human_cli.py`: 新AIと設定CLI、AI判断ログ
- `tests/test_search_agents.py`: 新要件の単体テスト
- `README.md`: 評価式、AI仕様、実行例

## タイムアウト

再帰探索はdeadline超過時に`SearchTimeout`を送出し、`0.0`や途中値を返さない。辺適用後の再帰はすべて`try/finally`で`undo_edge`する。ルートは完了済み候補の最善手、完了候補0なら事前評価先頭、事前評価0なら非`ん`辺優先のフォールバックを使う。

## 適応深度

Minimax、AlphaBeta、BeamNegamax、AggressivePVSは`AdaptiveDepthMixin`を共用する。各手で`current_depth`まで1回だけ探索し、反復深化は行わない。

- タイムアウト: 次手を1深度下げる
- 3回連続正常終了: 次手を1深度戻す
- 下限: `min_depth=1`
- 上限: 初期`depth`

## 評価関数

```text
score = attack_score + survival_weight * survival_score
```

attackの係数は常に1である。相手の合法単語数、安全単語数、安全辺数、安全終端文字数をそれぞれ`-12`、`-8`、`-6`、`-4`、危険単語数を`+2.5`で評価する。合法手または安全手が0なら勝ち候補とする。

survivalは相手の安全応手ごとに、その後自分に残る安全単語数`×4`、安全辺数`×8`、安全終端文字数`×6`を計算する。応手間の最悪値に、辺多重度で重み付けした平均の0.15を加える。この計算は探索再帰を呼ばず、局所辺集計だけを使う。

survival weightは`0.15 / 0.35 / 0.8 / 1.5`。安全単語数の閾値は`10 / 5 / 2`、安全辺数は`3 / 2 / 1`である。安全終端文字が1種類以下の場合も瀕死とする。すべて`EvaluationConfig`に集約した。

## 勝敗距離

`WIN_SCORE - ply`により短い勝ちを優先し、`LOSS_SCORE + ply`により同じ負けなら長く持ちこたえる手を優先する。

## BeamNegamax

標準深度5、ビーム幅`(24, 12, 6, 4)`。深さ4以降は4を使う。全候補を共通評価で並べ、幅外を`beam_pruned_move_count`として除外する。alpha-betaは使用しない。

## AggressivePVS

標準深度5。即時勝利、attack、総合値の順で候補を並べるが、局面評価は共通survivalを残す。最初の候補は通常窓、2本目以降はnull window。`alpha < score < beta`なら通常窓で再探索し、`score >= beta`なら枝刈りする。

## MonteCarlo

候補1の全試行後に候補2へ進む方式を廃止し、全候補を1回ずつ試すラウンドロビンにした。`playout_counts`をextraに記録する。

## 検証結果

- 初回実装時の自動テスト: 101件成功
- 構文検査: 成功
- D100、7AI、異なる先後手42対戦のスモーク: 完走、invalid move 0
- AlphaBeta/PVSの100個のランダム小規模グラフ比較: 最善辺と値が全件一致
- 4探索系AI: タイムアウト後`2→1`、3回成功後`1→2`を確認
- 辺状態: 通常、タイムアウト例外の両方で完全復元

## 懸念

- 新評価は相手応手の局所生存集計を行うため、旧評価より事前並べ替えコストが高い。deadlineで中断し、完了済み候補かフォールバックを使う。
- `branch_limit`を明示するとMinimax/AlphaBetaは後方互換の候補制限を行う。標準は`None`。
- 置換表、反復深化、アスピレーション窓、LMRは未実装。
