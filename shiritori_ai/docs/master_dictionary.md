# JMdictマスター辞書（辞書最適化・第一段階）

この処理は、辞書最適化の第一段階として、JMdictの読み・表記・sense・属性間の対応を失わずに保存するマスター辞書を作ります。既存AIが読む実験用CSVを置き換える処理ではありません。

辞書最適化は次の順で進めます。

1. JMdictから情報保持型のマスター辞書を作る（今回）
2. 品詞、固有名詞、古語、優先度、最小・最大文字数などを条件に実験用辞書を作る
3. 実験用辞書を文字ID、先頭・末尾文字別の行列、集合などへ変換する
4. AI対AIは有向多重グラフの辺数、人間対AIは単語と使用済み情報を管理する
5. 品詞構成、文字数分布、先頭・末尾文字分布、連結性を評価する

## 入力と実行方法

入力はJMdict XMLまたはgzip圧縮されたJMdictです。既存の取得コマンドはそのまま利用できます。

```bash
python src/dataset.py download --output data/raw/JMdict_e.gz

python src/dataset.py build-master \
  --input data/raw/JMdict_e.gz \
  --output data/master/master_dictionary.jsonl
```

出力先を省略せず指定します。副ファイルは標準で次の名前になります。

- `data/master/master_dictionary.metadata.json`: 入力・出力SHA256、生成日時、バージョン、主要件数
- `data/master/master_dictionary.stats.json`: 正規化、属性、開始・終了文字、文字数などの統計

`--metadata-output` と `--statistics-output` で個別に変更できます。入力がない、XMLが壊れている、出力できない場合は終了コード2とエラー理由を表示します。

## 正規化規則

規則バージョンは `legacy_v1` です。辞書生成と人間入力はどちらも `src/normalize.py` の同じ関数を使います。

処理順は次のとおりです。

1. 前後の空白を除き、Unicode NFKCで全角・半角や結合文字を正規化する
2. カタカナをひらがなへ変換する
3. 小書き仮名 `ぁぃぅぇぉゃゅょっゎゕゖ` を対応する大きい仮名へ変換する
4. `ゐ→い`、`ゑ→え`、`ぢ→じ`、`づ→ず`、`ゔ→ぶ` とする
5. 長音記号を直前の音の母音へ変換する
6. ひらがな以外が残る読み、空文字、解決できない長音を拒否する

現行互換性のため、`legacy_v1` は正規化後1文字の読みも `too_short` として拒否します。マスター生成側ではそれ以外の最小・最大文字数制限を行いません。`ん`で終わる読みは保存します。濁音・半濁音は上記の明示変換以外では区別します。

失敗理由は `empty`、`too_short`、`contains_non_hiragana`、`unresolvable_long_vowel` です。

## 文字数

`normalized_length` は、NFKCを含む上記正規化が終わった `normalized_reading` に対するPythonの `len()` です。第二段階の最小・最大文字数条件にはこの値を使います。

`original_reading_lengths` は、元の `reb` とその未正規化文字列に対する `len()` の対応表です。結合文字の合成などにより、元の長さと `normalized_length` が異なる場合があります。同じ元読みは一度だけ保存します。

## JMdict属性の対応

一つのレコードは一つの `normalized_reading` です。同じ正規化読みになった複数entry・読みは統合します。元情報は `original_readings`、`entry_ids`、`sources`、`applicable_senses` に保持します。

- `re_nokanji` がある読みは漢字表記を対応させない
- `re_restr` がある読みは指定された `keb` だけを対応させる
- `stagr` があるsenseは指定された元読みだけへ適用する
- `stagk` があるsenseは、読みが許可する表記との積集合だけへ適用する
- `pos` が省略されたsenseは、同じentry内の直前の明示 `pos` を引き継ぐ
- `pos_tags`、`misc_tags`、`field_tags`、`dialect_tags` と派生真偽値は、当該読みの `applicable_senses` だけから集約する
- XMLパーサーがDTD entityを説明文へ展開した場合は、`src/jmdict_tags.py` が元の短いentityコードへ戻す

`sources` はentry・元読み単位で、`re_nokanji`、`re_restr`、`re_inf`、`re_pri`、対応表記ごとの `ke_inf` と `ke_pri` を保持します。これにより、正規化読みへ統合した後も表記・読みの関連を復元できます。

優先度は `3=high`、`2=medium`、`1=low` です。`news1/ichi1/spec1/gai1/nf01..nf05` を高、`news2/ichi2/spec2/gai2/nf06..nf10` を中、その他を低とし、複数タグでは最高値を採用します。元タグは削除しません。

品詞・属性の分類集合も `src/jmdict_tags.py` に集約しています。名詞候補は `n`、`n-adv`、`n-t`、`n-pref`、`n-suf`、`num`、`pn` です。`vs`（サ変可能）だけでは名詞候補にしません。固有名詞専用の派生判定は持たず、取得できた値は `pos_tags` と品詞統計へそのまま残します。動詞は `v` で始まる品詞、形容詞は `adj-` で始まる品詞です。古語・廃語・まれな語はそれぞれ `arch`、`obs`、`rare`、方言は `dial` の存在、専門分野は `field` の存在で判定します。

## JSON Lines形式

UTF-8で、一行に一つのJSON objectを書きます。行は `normalized_reading` の辞書順です。集合由来の配列と `applicable_senses` も安定ソートされ、同じ入力から同じJSONLバイト列を生成します。

主要フィールドは次のとおりです。

- 読み: `normalized_reading`、`normalized_length`、`original_readings`、`original_reading_lengths`
- 表記・出典: `spellings`、`entry_ids`、`sources`
- タグ: `priority_tags`、`priority_level`、`pos_tags`、`misc_tags`、`field_tags`、`dialect_tags`、`reading_info_tags`、`kanji_info_tags`
- しりとり用派生値: `start_char`、`end_char`、`ends_with_n`
- 条件抽出用派生値: `has_noun_sense`、`has_verb_sense`、`has_adjective_sense`、`has_archaic_sense`、`has_obsolete_sense`、`has_rare_sense`、`has_dialect_sense`、`has_specialized_sense`
- sense対応: `applicable_senses`

`applicable_senses` は `entry_id`、元の `reading`、`sense_number`、`applicable_spellings`、各種タグ、gloss、`s_inf`、元の `stagk`/`stagr` を保存します。glossは本文、言語、種別、性を保持します。

## 統計ファイル

統計JSONにはentry・表記・読み・候補数、正規化成功・失敗、理由別失敗数、統合前後件数、重複統合数、優先度別・品詞タグ別件数、派生属性別件数、`ん`終わり、先頭・末尾文字分布を保存します。

`normalized_length_word_counts` は文字数を文字列キー、語数を整数値とする分布です。あわせて `minimum_normalized_length`、`maximum_normalized_length`、`average_normalized_length` を保存します。

## テスト

外部ファイルやネットワークに依存しないfixtureを使います。

```bash
python -m unittest discover -s tests -v
```

fixtureは正規化、文字数、重複統合、`re_restr`、`stagk`、`stagr`、品詞継承、優先度、安定出力、メタデータ・統計を検証します。

## 後続段階との接続

この文書の対象である第一段階には、実験用辞書、文字ID、辺数管理、単語バケット、ゲーム状態は含まれません。現在は後続段階として`src/experiment_dictionary.py`と`src/runtime_dictionary.py`が実装されており、実験辞書生成時に一行一語TXT、詳細JSONL、単語確認CSV、辺確認CSV、RuntimeDictionary JSONを同時生成します。探索エージェント自体の高速化、完全解析の変更、HybridAgentは引き続き対象外です。
