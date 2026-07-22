# 辞書最適化・実装計画

## 目的

JMdict由来の情報保持型マスター辞書から、再現可能な名詞実験辞書、探索用`RuntimeDictionary`、辺数中心の対局状態、辞書分析までを五段階で接続する。探索アルゴリズム、評価関数、探索深度、完全解析は変更しない。

## 確認した既存構成

- JMdict解析・取得・旧実験辞書生成: `src/dataset.py`
- 共通読み正規化: `src/normalize.py`
- 第一段階マスター生成: `src/master_dictionary.py`、`src/jmdict_tags.py`
- 旧辞書形式: `reading,start_char,end_char,priority_rank,priority_label,priority_tags`を持つCSV
- 旧ランダム抽出: `dataset.select_records`
- 辞書グラフ: `src/game.py`の`WordGraph`
- 近似AI状態: `src/agents.py`の`GameState(current_char, used_ids)`
- AI対AI: `src/match.py`の`simulate_match`
- 人間対AI: `src/human_cli.py`
- 完全解析: `src/exact_solver.py`の`ShiritoriSolver(current_char, used_mask)`
- 実験入口: `src/experiments_exact.py`、`src/experiments_approx.py`
- 既存統計: `src/dictionary_stats.py`
- テスト: `tests/test_normalize.py`、`test_dataset.py`、`test_master_dictionary.py`、`test_solver.py`、`test_agents_match.py`

作業開始時点で、実験結果、図、既存ソースに未コミット変更が多数ある。今回の変更は辞書最適化に必要なファイルへ限定し、既存変更を戻さない。

## 段階別計画

### 第一段階: マスター辞書

既存実装を維持し、不足だけを修正する。

- `n-pr`専用派生フラグと統計を削除する。`pos_tags`自体は入力情報として保持する。
- 名詞候補を`n`、`n-adv`、`n-t`、`n-pref`、`n-suf`、`num`、`pn`で判定する。
- `vs`単独を名詞扱いしない。
- 名詞候補数を統計へ追加する。
- fixture、実JMdict、安定出力を再検証する。

### 第二段階: 実験用辞書

新規`src/experiment_dictionary.py`を追加する。

- 入力はマスターJSONLだけとし、JMdict XMLを解析しない。
- `has_noun_sense`、`normalized_length`で候補を作る。
- 優先度レベルごとにローカル`random.Random(seed)`で安定シャッフルし、全条件で共通の順位を作る。
- 文字数条件は共通順位へのフィルタとして適用し、サイズはprefix抽出して包含関係を保証する。
- 一行一語TXT、詳細JSONL、メタデータ、統計を出力する。
- 語数不足は既定でエラー、`--allow-smaller`時だけ許可する。

### 第三段階: RuntimeDictionary

新規`src/runtime_dictionary.py`を追加する。

- 詳細JSONLから不変な実行時辞書を構築する。
- 文字IDは、既存`normalize_game_char`を適用した開始・終了文字集合の辞書順で割り当てる。
- `edge_counts`は一次元配列`start_id * char_count + end_id`とする。
- バケットはCSR形式の`bucket_offsets`と`bucket_word_ids`で保持する。
- `active_end_masks`はPython整数ビット集合とする。
- JSON保存・読込、構造検証、旧`WordGraph`との一致検証を実装する。
- 通常テストとは別に`benchmarks/dictionary_runtime_benchmark.py`を追加する。

### 第四段階: 状態管理

新規`src/runtime_state.py`を追加し、`src/match.py`へ新方式の対局入口だけを追加する。

- AI対AI用`AIEdgeState`: `required_char_id`、辺数、active mask、辺履歴だけを持つ。
- `apply_edge`/`undo_edge`を定数時間にする。
- 表示時に辺履歴をバケット順の異なる具体語へ決定的に割り当てる。
- 人間対AI用`HumanRuntimeState`: `used_word_ids`、`bucket_cursors`、具体語履歴を追加する。
- 人間入力は共通正規化を使い、失敗理由を返す。
- 既存AIアダプタは辺履歴を具体word ID集合へ決定的に復元し、既存`GameState`と`WordGraph`を渡す。AI実装は変更しない。
- 旧`simulate_match`と旧`human_cli`経路は削除しない。

### 第五段階: 辞書分析

新規`src/dictionary_analysis.py`を追加する。

- 基本統計、入出辺、辺種類、弱連結成分、Tarjan法による強連結成分を標準ライブラリで計算する。
- 最大文字数比較と辞書サイズ比較は第二段階の共通順位を再利用する。
- JSON、CSV、既存matplotlibによる図を出力する。
- AI勝率実験とは分離する。

## 段階間の不変条件

- `normalized_reading`はマスターから実験辞書へ変更しない。
- 実験辞書の`word_id`は出力順の連番であり、RuntimeDictionaryでも維持する。
- `word_start_ids`、`word_end_ids`は`normalize_game_char`後の文字と対応する。
- 同じマスター、条件、seedから同じTXT/JSONLを生成する。
- 同じ文字数条件とseedでは、小さい辞書が大きい辞書のprefixかつ部分集合になる。
- RuntimeDictionaryの総辺数、全バケット語数、単語数は一致する。
- 旧`WordGraph`と新方式で、開始文字別語数、移動可能末尾文字、辺別語数、`ん`終端数を一致させる。

## 性能測定

通常テストの合否とは分離し、次を`perf_counter`と概算オブジェクトサイズで測る。

- 旧辞書読込と詳細JSONL読込
- RuntimeDictionary構築
- 合法単語列挙
- 利用可能末尾文字列挙
- apply/undo
- edge countsコピー
- 旧used set状態と新辺数状態のメモリ概算

## 簡略化方針

- 外部依存は追加しない。
- 言語学的な追加分類は行わず、名詞候補、優先度、文字数を主要条件とする。
- 固有名詞専用判定は削除し、取得できたposタグ統計だけを残す。
- RuntimeDictionaryはPython標準型を使い、NumPy等は導入しない。
- 既存AIはアダプタ経由で再利用し、探索コードを二重実装しない。

## 完了条件

各段階で自動テスト、既存方式との比較、段階レポートを完了してから次へ進む。最後に全テスト、実JMdictからの再生成、実験辞書、RuntimeDictionary、分析、小規模AI対局、人間入力状態確認、性能比較を実行し、`final_report.md`へ結果を記録する。
