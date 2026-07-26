# 盤面適応型ハイブリッド（第二段階）

> [!IMPORTANT]
> この文書はコミット`c4ad512`時点の修正前計画である。動的Beamの
> 再帰幅不適用を直したv2の設計・コマンドは
> [`position_adaptive_hybrid_v2_report.md`](position_adaptive_hybrid_v2_report.md)
> を参照する。修正前と修正後の結果は混ぜない。
>
> 実験状態: D10000・180局で完了。予定していた440局の独立最終評価は
> 実行しない。結果と採用判断は
> [`position_adaptive_hybrid_experiment_result.md`](position_adaptive_hybrid_experiment_result.md)
> を参照。

## 目的

ハイブリッド第一段階で有力だったBeamAlphaBetaとBeamPVSを基礎に、
盤面規模と一手内の探索実績から探索方式を切り替える。既存の評価関数、
候補順序、辺専用`AIEdgeState`、apply/undo、適応深度は変更していない。

## 事前確認

- `AlphaBetaAgent`: 深度制限付き。通常設定では`branch_limit=8`であり、
  終局まで読む完全解析ではない。
- `BeamAlphaBetaAgent` / `BeamPVSAgent`: 現在の標準値は初期深度8、
  最大深度9、幅`12,8,4,2`。
- `ShiritoriSolver`: 辺の残数を混合基数で符号化するメモ化完全解析。
  D300の過去結果でも数万状態で終わる局面と数千万状態で制限超過する局面が
  混在するため、辞書全体の大きさだけでは安全に切り替えられない。
- D10000追試のroot候補数は中央値24、90 percentile 41、
  95 percentile 47。これを動的幅の初期閾値に使った。
- BeamPVSは平均探索効率がやや良い一方、再探索が集中した局面で時間切れ
  しやすい。これが再探索適応型の仮説である。

## 実装した6手法

1. `branch_switch_alpha_beta`
   - rootの合法辺種類数が12以下なら候補を削らないAlphaBeta。
   - 13以上なら固定幅BeamAlphaBeta。
2. `dynamic_beam_alpha_beta`
   - 各探索ノードで候補数6以下は全件、7–24は幅12、
     25–48は幅8、49以上は幅6。
   - さらにply別上限`12,8,4,2`を適用する。
3. `dynamic_beam_pvs`
   - 2と同じ動的幅をPVSへ適用する。
4. `research_adaptive_beam`
   - 一手を一つの反復深化として管理し、既定では深度7から開始する。
   - 合法辺が多く安全語も十分ならBeamPVSから開始する。
   - PVS再探索率が4%超、または次深度の予測時間が残り時間の80%超なら
     次深度をBeamAlphaBetaへ切り替える。
   - 次深度が失敗した場合は直前に完了した深度の合法手を返す。
5. `endgame_exact_hybrid`
   - 通常はBeamAlphaBeta。到達可能な残存部分が
     32語、18辺種類、12文字、推定20万状態以下の全条件を満たす場合だけ
     `ShiritoriSolver`を呼ぶ。
   - 完全解析の上限は20万状態、かつ一手制限の20%または0.2秒の短い方。
   - 制限超過時は解析開始前に保存した合法手へ戻る。
6. `integrated_adaptive_hybrid`
   - 完全解析条件なら完全解析。
   - 対象外で合法辺12以下なら候補を削らないAlphaBeta。
   - それ以外では再探索適応型を使用する。

閾値は`AdaptiveHybridConfig`へ集約した。通常CLIでも変更でき、実験では
`conservative`、`balanced`、`aggressive`の3設定だけを調整用seedで比較する。
候補の全組合せ探索は行わない。

## 完全解析の定義

通常AlphaBetaは指定深度で評価関数を返す近似探索である。完全解析は、
現在位置から到達できる残存辺の使用回数を状態へ含め、勝敗が確定する終局まで
再帰する。`ん`へ向かう辺は即時敗北として既存規則を維持する。

切替判定では、単なる現在の合法手数ではなく、到達可能語数、辺種類数、
文字頂点数、各辺の残数から得る状態数上界を使う。上界は保守的であり、
実際の到達状態数より大きくなる場合がある。

## 適応深度と時間管理

分岐切替、動的幅、終盤完全探索型は既存の手単位適応深度を再利用する。
再探索適応型と統合型は一手の反復深化を自分で管理する。深度ごとの方式変更に
既存エージェントを別々に呼ばないため、異なる方式の時間履歴が別の
`current_depth`を誤って変更することはない。完了深度だけを採用し、
失敗中の探索はapply/undoの`finally`で復元される。

## ログ

既存項目に加えて次を対局履歴へ保存する。

- `search_mode`, `mode_history`, `switch_reason`, `mode_counts`
- `mode_switch_count`, `completed_iterative_depth`
- `dynamic_beam_width_counts`, ply別候補数・選択数
- `predicted_next_depth_time_sec`, `position_scale`, `exact_gate`
- `exact_attempt_count`, `exact_success_count`, `exact_timeout_count`
- `exact_limit_count`, `exact_state_count`, `exact_result`
- `fallback_count`

`exact_timeout_count`は時間超過だけ、`exact_limit_count`は時間または状態上限を
含む全制限超過を数える。

## 実験設計

### 段階1: 調整

- D10000、辞書seed 0–4
- 3 profile × 6新手法 × BeamAlphaBetaとの先後入替
- 180局
- 一手1秒、最大1000手、対局最大300秒
- 一局45秒と仮置きした概算は約2.3時間

集計器は新手法全体のBeamAlphaBetaに対する勝率を最大化し、同率なら
timeout数、平均思考時間の順にprofileを一つ選ぶ。最終評価結果を見て
profileを変更してはならない。

### 段階2: 最終評価

- D10000、未使用の辞書seed 10–29
- BeamAlphaBetaを共通アンカーにした8組と、仮説を直接検証する3組
- 各組を各seedで先後入替
- 11組 × 20 seed × 2席 = 440局
- 一局45秒の概算は約5.5時間。全局が300秒上限まで達する最悪値は
  約36.7時間

同一seed・先後に対応する構造を保つ。勝率にはWilson 95%区間、
直接対戦には両側exact binomial testを出す。20局だけの追試より差の
推定は改善するが、440局でも小差を確定できない可能性は残る。

### 段階3: 固定局面

既存の保存14局面を全9手法で固定深度8探索する（126判断）。
時間制限付き対局の差を、
探索方式・候補制限・ノード数の差から分離する補助実験である。

## 実行方法

調整実験:

```bash
.venv/bin/python -u src/run_position_adaptive_hybrid_experiment.py \
  --stage tune
```

同じコマンドを再実行すると、同じコード・設定hashの出力先にある
`match_id`を読み、完了済み対局を飛ばす。
未完了runを集計しても途中経過は出るが、誤選定を防ぐため
`selected_profile.json`は全180局が完了するまで生成されない。

調整結果の集計:

```bash
TUNE_DIR=$(ls -td results/position_adaptive_hybrid/tune/D10000/* | head -1)
.venv/bin/python src/analyze_position_adaptive_hybrid_experiment.py \
  --input "$TUNE_DIR"
```

各実験コマンドに`--analyze`を付ければ、その呼び出し終了後に同じ集計を
自動実行できる。

最終評価用辞書:

```bash
.venv/bin/python src/experiment_dictionary.py \
  --master data/master/master_dictionary.jsonl \
  --size 10000 \
  --seeds 10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29 \
  --min-length 2 \
  --max-length 12 \
  --output data/dictionaries
```

最終評価:

```bash
.venv/bin/python -u src/run_position_adaptive_hybrid_experiment.py \
  --stage final \
  --selection-from "$TUNE_DIR/analysis/selected_profile.json"
```

最終集計:

```bash
FINAL_DIR=$(ls -td results/position_adaptive_hybrid/final/D10000/* | head -1)
.venv/bin/python src/analyze_position_adaptive_hybrid_experiment.py \
  --input "$FINAL_DIR"
```

固定局面:

```bash
.venv/bin/python -u src/run_position_adaptive_hybrid_experiment.py \
  --stage fixed \
  --selection-from "$TUNE_DIR/analysis/selected_profile.json"
```

## 出力

各runに`manifest.json`、`completion.json`、`raw_matches.jsonl/csv`、
失敗時の`failures.jsonl`を置く。分析先には`agent_summary`、
`direct_matchups.csv`、`mode_usage.csv`、動的幅使用表、完全解析試行表、
値付き勝率・思考時間・完全解析成功率グラフ、Markdownレポートを置く。

## テストとスモークテスト

```bash
.venv/bin/python -m unittest discover -s tests
```

外部辞書に依存しない小辞書で、合法性、決定性、状態復元、適応深度、
全切替、動的幅上限、PVS再探索切替、完全解析、制限時fallback、
factory、実験件数、seed分離、profile選定、分析出力を検査する。

実装完了時は全205テストが成功した。10語の一時辞書では
`--match-limit 2`の調整runを同じコマンドで二度呼び、完了数が2から4へ
増えて既存2局が再実行されないことを確認した。途中結果のCSV/JSON、
値付きPNGも生成できた。固定局面は1局面・1エージェントの短時間実行と
分析まで確認した。D10000本実験は実行していない。

## 変更ファイル

- 新規: `src/adaptive_hybrid.py`
- 新規: `src/run_position_adaptive_hybrid_experiment.py`
- 新規: `src/analyze_position_adaptive_hybrid_experiment.py`
- 新規: `tests/test_adaptive_hybrid.py`
- 新規: `tests/test_position_adaptive_hybrid_experiment.py`
- 新規: 本文書
- 接続・ログ拡張: `src/agents.py`, `src/search_common.py`,
  `src/match.py`, `src/human_cli.py`, `src/experiments_approx.py`,
  `src/run_graph_control_comparison.py`
- 利用方法: `README.md`

## 懸念と本実験後に見る項目

- 初手の候補数は後半より極端に多く、全体平均だけでは動的幅を評価できない。
  `mode_usage.csv`を残存規模別に見る。
- 状態数推定は上界であり、解ける終盤を見送る場合がある。まず誤った
  切替による通常探索時間の損失を避ける保守設定とした。
- 完全解析成功が増えても、その局面が元からBeamAlphaBetaと同じ手なら
  勝率は改善しない。固定局面で選択手の一致率を確認する。
- PVSからAlphaBetaへの切替が多すぎる場合は、再探索率だけでなく
  予測時間側の発火割合を確認する。
- 統合型が単純型を上回らなければ、複雑性を標準設定へ採用しない。
