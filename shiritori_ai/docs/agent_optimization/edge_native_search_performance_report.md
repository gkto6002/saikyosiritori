# 辺ネイティブ探索高速化レポート

## 目的

`RuntimeDictionary`、`EdgeDictionary`、`AIEdgeState`を用いるAI対AI探索について、攻撃と生存を組み合わせる評価方針、Negamax、AlphaBeta、Beam Negamax、PVSの基本構造を維持しながら、重複する辺走査と過剰な完全生存評価を削減する。

置換表、Zobrist Hash、反復深化、アスピレーション窓、Late Move Reduction、新エージェントは導入していない。

## 変更前の確認

変更前は、`_score_edge_candidates`が候補順序付けの全候補に`evaluate_edge_candidate`を呼び、各候補について相手の安全応手を一つずつ`apply_edge`して完全生存評価を行っていた。D20000、seed 0・1・2、0.3秒の固定一手計測では、AlphaBeta、Beam Negamax、Aggressive PVSの9/9実行がルート順序付け中にタイムアウトした。

- 平均経過時間: 各AIとも約0.300秒
- タイムアウト率: 100%
- 完了ルート候補: 0
- 探索ノード: 0
- 順序付け時間: 0.2996〜0.2997秒
- 完全生存評価: 一手平均123.7〜132.7回

## 変更したファイル

- `src/runtime_state.py`
- `src/search_common.py`
- `src/agents.py`
- `src/match.py`
- `src/experiments_approx.py`
- `src/human_cli.py`
- `tests/test_runtime_state.py`
- `tests/test_search_agents.py`
- `tests/test_agents_match.py`
- `README.md`

## 追加したファイル

- `benchmarks/edge_search_benchmark.py`
- `docs/agent_optimization/edge_native_search_performance_report.md`

## AIEdgeStateの集計値

各開始文字について次を初期化時に一度計算し、探索中は配列から取得する。

- `remaining_word_counts`
- `remaining_safe_word_counts`
- `active_edge_type_counts`
- `active_safe_edge_type_counts`
- `destination_masks`
- `safe_destination_masks`

`edge_position_metrics`は、通常の探索局面では`required_char_id`に対応する配列要素と整数ビットマスクの`bit_count`だけを読み、辺行全体を走査しない。

`apply_edge`は単語数を常に1減らす。残数が1から0になる場合だけ、辺種類数を1減らし、終端文字ビットを消す。`ん`辺はsafe系集計を変更しない。

`undo_edge`は完全な逆操作を行う。残数が0から1になる場合だけ、辺種類数と終端文字ビットを復元する。`assert_aggregates_consistent`は辺行列から集計値を再計算し、六配列と`active_end_masks`の一致をテスト・デバッグ時に検証する。

## 評価の呼び分け

候補順序付けでは`evaluate_ordering_score`を使用する。候補を一度適用した後の相手の合法単語数、安全単語数、辺種類数、終端文字マスクを集計配列から読み、攻撃評価だけを返す。相手の応手を適用する完全生存評価は呼ばない。即時勝利は最上位、`ん`終端は最下位となる。

探索末端の辺評価は次の四段階である。

| 危険度 | 条件 | 生存評価 | 重み |
|---|---|---|---:|
| 通常 | 安全単語11以上かつ安全辺4種類以上 | なし。攻撃評価のみ | 0.0 |
| 注意 | 安全単語10以下または安全辺3種類以下 | 現在集計値だけの簡易評価 | 0.35 |
| 危険 | 安全単語5以下または安全辺2種類以下 | 相手の安全応手を調べる完全評価 | 0.8 |
| 瀕死 | 安全単語2以下または安全辺1種類以下 | 相手の安全応手を調べる完全評価 | 1.5 |

完全評価では、各安全応手後の自分の安全単語数、安全辺種類数、安全終端文字種類数を使い、最悪値を中心に辺多重度付き平均の0.15を加える従来方針を維持した。攻撃評価はすべての段階で残る。

## 候補上限

全候補へ軽量評価を行った後、探索対象だけを上位から取得する。D20000 seed0の2,895辺から上位12辺を得るマイクロベンチマークでは、全ソート1.363秒、`heapq.nsmallest` 0.575秒（各2,000回）で、結果は一致し、後者が2.37倍速かった。このため候補上限が全候補数より小さい場合は`heapq.nsmallest`を使用する。

即時勝利辺は軽量評価で最高点になるため、候補上限やビーム幅の外へ落ちない。

## 新しい標準設定

- Minimax: 深度3、`branch_limit=12`
- AlphaBeta: 深度3、`branch_limit=12`
- Beam Negamax: 深度4、`beam_widths=(12, 8, 4, 2)`、以降は2
- Aggressive PVS: 深度3、`branch_limit=12`
- 深度回復に必要な高速完了: 5回

CLIとコンストラクタで明示した深度、候補上限、ビーム幅、回復回数は標準値より優先される。AlphaBetaとAggressive PVSの標準深度・候補上限を同じにした。

## ソフトタイムアウト

一手時間を制限時間で割った`elapsed_ratio`を記録する。

- ハードタイムアウトまたは`elapsed_ratio >= 0.9`: 次手の深度を1下げ、回復回数を0へ戻す
- `0.8 <= elapsed_ratio < 0.9`: 深度を維持し、回復回数へ加算しない
- `elapsed_ratio <= 0.5`: 高速完了として加算し、5回連続で深度を1戻す
- その他: 深度を維持し、連続高速完了回数を0へ戻す

深度は`min_depth`未満、初期最大深度より上にはならない。一手につき深度調整はルート終了時の一回だけ行う。

## 追加した計測

探索結果の`extra`と対局の一手ログへ次を追加した。

- `ordering_time_sec`
- `evaluation_time_sec`
- `search_time_sec`
- `total_search_time_sec`
- `nodes_searched`
- `leaf_evaluations`
- `ordering_evaluations`
- `full_survival_evaluations`
- `simple_survival_evaluations`
- `completed_root_moves`
- `effective_depth`
- `next_depth`
- `elapsed_ratio`
- `timed_out`
- `null_window_searches`
- `research_count`
- `research_rate`
- `cutoff_count`
- `beam_pruned_move_count`

時間計測は候補順序付け、末端評価、ルート探索全体という大きな処理単位で行い、再帰呼出しごとの`perf_counter`は追加していない。

## 固定一手ベンチマーク

条件:

- 辞書: D20000、seed 0・1・2
- 制限時間: 0.3秒
- AlphaBeta: 深度3、候補12
- Beam Negamax: 深度4、幅12・8・4・2
- Aggressive PVS: 深度3、候補12
- 各辞書の初期局面から一手

| AI | 変更前平均秒 | 変更後平均秒 | 高速化 | timeout前→後 | 平均ノード | ordering秒 | evaluation秒 | 完了ルート | 完全生存評価 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AlphaBeta | 0.3001 | 0.0603 | 4.98倍 | 100%→0% | 577.7 | 0.0246 | 0.0320 | 12 | 0 |
| Beam Negamax | 0.3001 | 0.0924 | 3.25倍 | 100%→0% | 1260.0 | 0.0416 | 0.0450 | 12 | 0 |
| Aggressive PVS | 0.3001 | 0.0272 | 11.04倍 | 100%→0% | 207.7 | 0.0101 | 0.0157 | 12 | 0 |

初期局面は通常状態だったため、変更後の完全生存評価は0回である。PVSの再探索率は0.60%だった。

結果JSON:

- `results/edge_search_optimization/after.json`

## 対局スモーク

条件:

- runtime: D20000 seed 0・1・2
- agents: AlphaBeta、Beam Negamax、Aggressive PVS
- repetitions: 1
- `time_limit_sec=0.3`
- `max_moves=500`
- `max_match_time_sec=90`

18対局、合計3,272手を実行した。

- 全18対局完走
- 一手内部タイムアウト: 0
- 不正手: 0
- 試合時間上限: 0
- 終了理由: 全18対局が`ended_with_n`

| AI | 手数 | 一手平均秒 | timeout | 平均ノード | ordering秒 | evaluation秒 | 完全生存評価/手 | PVS再探索率 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| AlphaBeta | 1,267 | 0.0407 | 0 | 417.8 | 0.0133 | 0.0251 | 8.23 | - |
| Beam Negamax | 738 | 0.0926 | 0 | 1191.7 | 0.0364 | 0.0505 | 43.86 | - |
| Aggressive PVS | 1,267 | 0.0244 | 0 | 222.1 | 0.0054 | 0.0177 | 2.31 | 2.64% |

結果ディレクトリ:

- `results/edge_search_optimization/smoke_D20000_after`

## テスト

追加・更新した確認:

- 初期集計値と辺行列からの再計算の一致
- 2→1で辺種類数とマスクが変わらない
- 1→0で辺種類数とマスクが消える
- 0→1のundoで完全復元する
- `ん`辺がsafe集計へ入らない
- タイムアウト例外後に六集計配列を含む状態全体が復元する
- 通常・注意・危険・瀕死の評価呼び分け
- 順序付けが完全生存評価を呼ばない
- 即時勝利が候補上限1でも残る
- ハード・90%・80%・50%の共通深度調整
- 標準深度、候補上限、ビーム幅
- 小規模既知局面のAlphaBetaとPVSの最善辺・値の一致
- `extra`の時間・評価カウンタ

実行コマンド:

```bash
.venv/bin/python -m py_compile src/*.py benchmarks/*.py
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python benchmarks/edge_search_benchmark.py \
  --runtime \
    data/dictionaries/D20000_L2-12_seed0.runtime.json \
    data/dictionaries/D20000_L2-12_seed1.runtime.json \
    data/dictionaries/D20000_L2-12_seed2.runtime.json \
  --time-limit-sec 0.3 --repetitions 1 \
  --output results/edge_search_optimization/after.json
.venv/bin/python src/experiments_approx.py \
  --runtime \
    data/dictionaries/D20000_L2-12_seed0.runtime.json \
    data/dictionaries/D20000_L2-12_seed1.runtime.json \
    data/dictionaries/D20000_L2-12_seed2.runtime.json \
  --agents alpha_beta beam_negamax aggressive_pvs \
  --repetitions 1 --time-limit-sec 0.3 \
  --max-moves 500 --max-match-time-sec 90 \
  --output-dir results/edge_search_optimization/smoke_D20000_after
```

全106テストが成功し、失敗は0だった。

## 最善手と勝敗傾向

小規模既知局面ではAlphaBetaとPVSが従来テストと同じ`う→え`を選び、探索値も一致した。即時勝利・即時敗北の判定も維持した。

変更前のD20000対局はルート順序付けタイムアウトが続き、同一条件の18対局を完走できていなかったため、勝敗率の厳密な前後比較はできない。今回は標準深度と候補上限も指定どおり変更しているため、今回の18対局の勝敗を旧設定の勝敗と直接比較しない。

## 残る性能上の問題

- Beam Negamaxは枝刈りを行わないため、平均ノード数と完全生存評価回数が三手法中で最大である。
- 危険・瀕死局面では意図的に完全生存評価を残しており、終盤はevaluation時間の比率が上がる。
- ルートでは全辺種類へ軽量評価を行う。Dがさらに増えて辺種類数が増える場合、この部分が次のボトルネックになり得る。
- 置換表など、今回対象外の探索強化は未実装である。
