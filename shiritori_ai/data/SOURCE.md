# データ出典

## JMdict

本実験ではJMdictから抽出した読み仮名を使用します。JMdict/EDICTはElectronic Dictionary Research and Development Group（EDRDG）により提供されています。

- 取得URL: `http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz`
- プロジェクト情報: `https://www.edrdg.org/wiki/index.php/JMdict-EDICT_Dictionary_Project`
- ライセンス: Creative Commons Attribution-ShareAlike 4.0
- ライセンス文書: `https://www.edrdg.org/edrdg/licence.html`

JMdict rawファイルはサイズが大きく日次更新されるため、Git管理対象にはしません。取得日時、処理条件、辞書サイズ、random_seedは実験設定JSONに保存します。

## sample_words.csv

`sample_words.csv` は、JMdictなどの外部辞書から抽出したものではありません。動作確認用に作成した自作の小規模サンプル読み仮名リストです。

レポートの本実験ではJMdict由来データを使用してください。このCSVはテスト、デバッグ、実装確認用です。

## processed_words.csv

`processed_words.csv` は、`sample_words.csv` を次のコマンドで正規化して生成した派生データです。

```bash
python src/preprocess.py --input data/sample_words.csv --output data/processed_words.csv
```

現時点の `processed_words.csv` は、互換確認用に残している自作サンプル由来データです。本実験用の辞書は `src/dataset.py` または各実験スクリプトからJMdictを指定して生成してください。
