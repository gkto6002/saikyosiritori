# 第四段階レポート: AI対AI・人間対AI状態

## 段階の目的

RuntimeDictionaryの辺数を使い、AI対AIでは具体的な使用済み単語集合を状態から除き、人間対AIでは正確な単語重複判定を維持する。既存AIの探索処理は変更しない。

## 確認した既存コード

- `src/agents.py`: `GameState(current_char, used_ids)`と全既存AI
- `src/match.py`: AI対AIの具体word ID管理
- `src/human_cli.py`: 共通正規化、辞書・使用済み・開始文字検証
- `src/game.py`: 旧合法語列挙
- 第三段階のRuntimeDictionary、CSRバケット、初期辺数

## 変更したファイル

- `src/match.py`: 並行入口`simulate_runtime_match`を追加
- `benchmarks/dictionary_runtime_benchmark.py`: apply/undo、load、copy、メモリ測定を追加

## 追加したファイル

- `src/runtime_state.py`
- `tests/test_runtime_state.py`
- 本レポート

## 採用した設計

- `AIEdgeState`はrequired char、edge counts、active masks、edge historyだけを持つ。
- apply/undoは対象辺と対象ビットだけを更新する。
- 表示用word IDは、対局後に辺履歴の出現順とCSRバケット順から割り当てる。
- `HumanRuntimeState`はused word IDs、bucket cursors、word historyを追加する。
- cursorは探索開始位置だけに使い、使用済み判定は常にsetで行う。
- `RuntimeAgentAdapter`はAI呼出時だけ辺履歴を具体word IDへ復元し、既存`GameState`へ渡す。

## 実装した機能

- AI状態の利用可能辺/end列挙、合法語数・end種類数
- 辺apply/undoと0↔1時のmask更新
- 同一辺の残り本数までの反復使用
- 副作用なしの具体語割当
- 人間入力の理由付き正規化、辞書、使用済み、開始文字検証
- 人間によるバケット途中語の使用
- AIによる使用済み語スキップ
- 全バケットのデバッグ整合性検査
- 既存AIアダプタと新方式の小規模対局

## 実行したコマンド

```bash
.venv/bin/python -m unittest tests/test_runtime_state.py -v
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python benchmarks/dictionary_runtime_benchmark.py \
  --details data/dictionaries/D10000_L2-12_seed0.jsonl \
  --text data/dictionaries/D10000_L2-12_seed0.txt \
  --runtime data/runtime/D10000_L2-12_seed0.runtime.json \
  --repetitions 1000 \
  --output data/runtime/D10000_L2-12_seed0.benchmark.json
```

## テスト結果

- 第四段階テスト: 8件成功
- 全テスト: 67件成功
- apply/undo完全復元、mask更新、同一辺反復、語の重複防止、入力拒否、整合性: 全成功
- 既存Greedy/Randomを新状態アダプタ経由で実行: 成功

## 性能結果

D10000、1,000反復の参考値:

- apply+undo合計: 0.000475秒
- 旧used set（1,000 ID）コピー合計: 0.001949秒
- 新edge counts+maskコピー合計: 0.004401秒
- 旧TXT→WordGraph load: 0.003484秒
- Runtime JSON load+全検証: 0.010641秒
- WordGraph概算メモリ: 2,470,489 bytes
- RuntimeDictionary概算メモリ: 2,038,564 bytes
- AI辺状態の可変部分: 41,656 bytes
- 人間状態の可変部分: 78,948 bytes
- 旧used set 1,000語: 60,984 bytes

新方式は状態全体をノードごとにコピーするよりapply/undoで使うことを前提とする。時間値はテスト合否に使わない。

## 既存方式との比較

- 同じ読み一覧で初期総語数、開始文字別語数、移動可能end、辺別語数、`ん`語数が一致する。
- 一語使用後、旧方式はword IDをsetへ追加し、新方式は対応辺数を1減らす。対応する開始行の残り語数は一致する。
- 人間状態では同じword IDを二度使えない。
- AI状態では同じ辺をバケット語数まで使え、表示時は異なる単語になる。

## 発見した問題

- 既存AIは具体word IDを前提とするため、アダプタ内で一時的なmaterializationが必要であり、探索全体がまだ辺だけで動くわけではない。
- Runtime JSONは全配列を検証するため旧TXTよりロードが遅い。
- edge countsの全コピーは旧1,000要素setコピーより遅いため、探索ではapply/undoが必須である。

## 行った簡略化

- 既存AIを辺ネイティブに書き換えずアダプタで接続した。
- 人間CLI画面は変更せず、入力処理可能な状態クラスを独立追加した。
- 表示語は語彙順の決定的割当とし、表記選択ロジックは追加しない。

## 残っている問題

- 近似AI実験の標準CLIはまだ旧`simulate_match`を利用する。
- 各探索アルゴリズムを辺ネイティブ化する作業は、次の大項目「既存エージェント高速化」で行うべきである。

## 次の段階への引き継ぎ事項

- 第五段階はRuntimeDictionaryの初期辺数だけを分析し、可変対局状態や勝率と分離する。

## 後続改善: 全AIの辺ネイティブ化

後続のエージェント高速化作業でRandom、Greedy、Minimax、AlphaBeta、MonteCarloへ`choose_edge`を実装した。AI対AIでは単語フィールドを持たない`EdgeDictionary`だけを渡し、旧`RuntimeAgentAdapter`と辺履歴の単語materializationを削除した。`simulate_runtime_match`の履歴も辺ID・辺数だけとなり、具体語は保存しない。

人間対AIは`HumanRuntimeState`を標準経路へ接続した。AI思考中は辺状態のコピーだけを使い、確定した辺を`choose_ai_word`で未使用の具体語へ変換してから表示する。詳細は`docs/agent_optimization/edge_native_agents_report.md`を参照する。
- グラフ指標は文字IDグラフ上で計算する。
