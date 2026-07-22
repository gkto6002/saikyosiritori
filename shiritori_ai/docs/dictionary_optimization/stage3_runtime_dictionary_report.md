# 第三段階レポート: RuntimeDictionary

## 段階の目的

実験用詳細JSONLのword IDと読み順を維持したまま、文字ID、辺数、単語バケット、active end maskを持つ探索用不変辞書へ変換する。

## 確認した既存コード

- `src/game.py`の`WordGraph`、`by_start`、`normalize_game_char`
- `src/agents.py`と`src/exact_solver.py`の合法語列挙
- 第二段階の詳細JSONL形式とword ID

## 変更したファイル

- `.gitignore`: `data/runtime/`を追加
- `src/experiment_dictionary.py`: metadataへ正規化バージョンを追加

## 追加したファイル

- `src/runtime_dictionary.py`
- `tests/test_runtime_dictionary.py`
- `benchmarks/dictionary_runtime_benchmark.py`
- 本レポート

## 採用した設計

- RuntimeDictionary自体は`frozen dataclass`とし、初期値だけを保持する。
- 文字IDは、既存`normalize_game_char`適用後の出現文字集合を辞書順に並べる。
- `edge_counts[start_id * char_count + end_id]`の一次元配列を使う。
- バケットは`bucket_offsets`と`bucket_word_ids`のCSR形式にする。
- `active_end_masks[start_id]`はPython整数ビット集合にする。
- 可変な残り辺数は第四段階の状態へ分離する。

## 実装した機能

- 詳細JSONLからの構築
- JSON保存・読込
- char/word配列、word map、辺数、CSRバケット、active mask
- 全単語・辺数・文字・文字数・maskの整合性検証
- `WordGraph`への変換と旧方式比較
- 合法word ID、利用可能end ID、空・`ん`バケット処理
- 非ゲート型ベンチマーク

## 実行したコマンド

```bash
.venv/bin/python -m unittest tests/test_runtime_dictionary.py -v
.venv/bin/python src/runtime_dictionary.py \
  --input data/dictionaries/D10000_L2-12_seed0.jsonl \
  --output data/runtime/D10000_L2-12_seed0.runtime.json
.venv/bin/python benchmarks/dictionary_runtime_benchmark.py \
  --details data/dictionaries/D10000_L2-12_seed0.jsonl \
  --repetitions 1000 \
  --output data/runtime/D10000_L2-12_seed0.benchmark.json
.venv/bin/python -m unittest discover -s tests -v
```

## テスト結果

- 第三段階テスト: 7件成功
- 全テスト: 59件成功
- 旧`WordGraph`との語順、語数、開始文字別語数、辺別語数、`ん`終端数: 全一致

## 実データ結果

- word count: 10,000
- char count: 68
- 総辺数: 10,000
- 異なる辺種類数: 2,248
- 最大開始語数の文字: `し`、686語

## ベンチマーク結果

D10000、1,000反復の参考値:

- 詳細JSONL読込を含むRuntimeDictionary構築: 0.036711秒
- RuntimeからWordGraph構築: 0.002232秒
- 旧合法語列挙合計: 0.009126秒
- Runtime開始文字バケット取得合計: 0.000782秒
- Runtime末尾文字列挙合計: 0.004268秒
- edge countsコピー合計: 0.004290秒

時間値は環境依存であり、テスト合否には使っていない。

## 既存方式との比較

- 旧方式は開始文字から具体word IDを列挙し、使用済み集合で毎回フィルタする。
- 新辞書は開始・終了文字ごとの辺数とCSRバケットを事前計算する。
- 同じ読み一覧では全集計が一致した。
- `を→お`は旧`normalize_game_char`を再利用したため遷移も一致する。

## 発見した問題

- Python JSON形式は可読・検証しやすい一方、バイナリ形式よりロードサイズが大きい。
- edge countsコピーは4,624要素（68²）あり、探索ノードごとにコピーする設計は避けるべきである。

## 行った簡略化

- 固定かな表全体ではなく、辞書に出現する正規化ゲーム文字の辞書順を安定文字一覧とした。
- NumPyや専用ビット配列を追加せず、tuple/list/intを使用した。

## 残っている問題

- 可変辺数とapply/undoは未実装。
- RuntimeDictionaryを既存AIへ渡すアダプタは未実装。

## 次の段階への引き継ぎ事項

- 状態は`initial_edge_counts`と`initial_active_end_masks`をlistコピーして開始する。
- apply/undoは一辺だけ更新し、配列全体をコピーしない。
- 具体語表示はCSRバケットから決定的に割り当てる。
