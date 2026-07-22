# 第一段階レポート: マスター辞書

## 段階の目的

JMdictから、正規化読みをゲーム上の一語として統合しつつ、元の読み、表記、entry、sense、品詞、優先度、文字数を失わないJSON Linesマスター辞書を生成する。

## 確認した既存コード

- `src/dataset.py`: JMdict取得、旧CSV抽出、優先度付きseed抽出
- `src/normalize.py`: NFKC、カタカナ、小書き、長音、等価仮名、無効文字、2文字未満の拒否
- `src/master_dictionary.py`: entryのストリーム解析、制約付きsense対応、JSONL・副ファイル生成
- `src/jmdict_tags.py`: DTD entity短縮、優先度、品詞分類
- `tests/test_master_dictionary.py`とfixture
- `src/game.py`、`src/human_cli.py`: 同じ正規化と既存ゲーム文字規則の利用箇所

## 変更したファイル

- `src/jmdict_tags.py`
- `src/master_dictionary.py`
- `tests/fixtures/jmdict_master_fixture.xml`
- `tests/test_master_dictionary.py`
- `docs/master_dictionary.md`

## 追加したファイル

- 本レポート
- 全体計画 `docs/dictionary_optimization/implementation_plan.md`

## 採用した設計

- 既存第一段階を作り直さず不足だけを修正した。
- 固有名詞専用の`has_proper_noun_sense`と件数を削除した。未認識タグを含む`pos_tags`は情報保持のため残した。
- 名詞候補タグを`n`、`n-adv`、`n-t`、`n-pref`、`n-suf`、`num`、`pn`へ限定した。
- `vs`単独では名詞候補にしない。
- `re_restr`、`stagk`、`stagr`を交差判定し、集約属性は`applicable_senses`だけから生成する既存設計を維持した。

## 実装した機能

- `noun_candidate_count`統計
- 実験目的に合う`has_noun_sense`判定
- `n-pr`専用派生項目の削除
- 実JMdictによるマスター辞書再生成

## 実行したコマンド

```bash
.venv/bin/python -m unittest tests/test_normalize.py tests/test_master_dictionary.py -v
.venv/bin/python src/dataset.py build-master \
  --input data/raw/JMdict_e.gz \
  --output data/master/master_dictionary.jsonl
.venv/bin/python -m unittest discover -s tests -v
```

## テスト結果

- 第一段階関連: 16件成功
- 全テスト: 45件成功
- 実JMdict生成: 成功
- マスター辞書SHA256: `13f0e52aa4daca26a9e98ca85df70311d2aa34d2fc5c40891ba95cf90bbd7257`

## 実データ結果

- entry数: 217,743
- 読み候補数: 264,368
- 正規化成功数: 246,780
- 正規化失敗数: 17,588
- 統合後語数: 205,594
- 名詞候補数: 178,672
- 重複統合数: 41,186
- 最小・最大文字数: 2・37
- 平均文字数: 6.320836
- 優先度別: 高19,790、中7,833、低177,971
- 実データのposには`n`、`n-pref`、`n-suf`、`num`、`pn`等があり、`n-pr`はなかった。

## 既存方式との比較

旧`dataset.parse_jmdict`は読み、優先度、2〜12文字制限だけをCSVへ保存する。新マスターは文字数上限を設けず、同じ正規化関数を使い、表記・entry・sense関係を保持する。旧実験・AI経路は変更していない。

## 発見した問題

- 現行`legacy_v1`は正規化内で2文字未満を拒否し、第一段階でも620候補が`too_short`となる。
- 波ダッシュ等を含む16,965候補は`contains_non_hiragana`となる。
- 実JMdictに`n-pr`がないため、専用判定は研究用抽出に利用できない。

## 行った簡略化

- 固有名詞推定を表記やglossから行わない。
- 古語、方言、専門語等は保存するだけで除外しない。
- 言語学的に名詞とも解釈できる`adj-no`や`vs`は、明示された名詞系タグが同じ読みへ適用されない限り名詞候補にしない。

## 残っている問題

- 一文字語を保持する新正規化版は未実装。
- マスターJSONLは約303MBであり、第二段階はストリーム読込が必要。

## 次の段階への引き継ぎ事項

- 第二段階はJMdictを再解析せず、このマスターだけを読む。
- `has_noun_sense`、`normalized_length`、`priority_level`を主要抽出条件にする。
- マスターハッシュを全実験辞書メタデータへ保存する。
