# 辞書最適化・最終レポート

## 全体の実装概要

JMdictから情報保持型マスター辞書を生成し、そのマスターだけから再現可能な名詞実験辞書を生成し、文字ID・辺数・CSR単語バケットを持つRuntimeDictionaryへ変換した。さらに、AI対AI用の辺数状態、人間対AI用の具体語状態、辞書・文字グラフ分析を実装した。

既存Minimax、AlphaBeta、MonteCarlo、Greedy、Randomの評価・探索処理、探索深度、完全解析は変更していない。新方式は並行APIとアダプタとして追加し、旧方式を残した。

## 各段階で実装した内容

### 第一段階

- JMdict entry、読み、表記、制約付きsense、品詞、優先度、文字数をJSONLへ保存
- 同じ`normalized_reading`を一語へ統合
- `re_restr`、`stagk`、`stagr`、pos継承を処理
- `n-pr`専用派生判定を削除
- 名詞候補を`n/n-adv/n-t/n-pref/n-suf/num/pn`で判定
- メタデータ、SHA256、統計を保存

### 第二段階

- マスターだけを入力とする`ranked_noun_pool`
- 優先度3→2→1、同順位はローカルRandom(seed)による安定順序
- 最小・最大文字数フィルタ
- prefixによる辞書サイズ包含保証
- 一行一語TXT、詳細JSONL、metadata、stats
- 単一・複数サイズ、単一・複数最大文字数CLI

### 第三段階

- 安定したchar ID
- word ID、読み、長さ、開始・終了ID
- 一次元`initial_edge_counts`
- CSR形式`bucket_offsets/bucket_word_ids`
- 整数ビット集合`initial_active_end_masks`
- JSON保存・読込、全構造検証、旧WordGraph比較

### 第四段階

- `AIEdgeState`: required char、辺数、active mask、辺履歴
- 定数時間apply/undo
- 対局後の具体語割当
- `HumanRuntimeState`: used word IDs、bucket cursors、具体語履歴
- 理由付き人間入力検証と整合性検査
- 既存AIを変更しない`RuntimeAgentAdapter`
- 新方式対局`simulate_runtime_match`

### 第五段階

- 基本・文字数・優先度・開始終了文字統計
- 入出辺、辺種類、弱・強連結成分
- 最大文字数比較、辞書サイズ比較
- 詳細JSON、グラフJSON、CSV、matplotlib図

## 変更したファイル

- `.gitignore`
- `src/dataset.py`
- `src/normalize.py`
- `src/jmdict_tags.py`
- `src/master_dictionary.py`
- `src/game.py`
- `src/match.py`
- `tests/test_normalize.py`
- `tests/test_master_dictionary.py`
- `tests/fixtures/jmdict_master_fixture.xml`
- `docs/master_dictionary.md`

## 追加したファイル

- `src/experiment_dictionary.py`
- `src/runtime_dictionary.py`
- `src/runtime_state.py`
- `src/dictionary_analysis.py`
- `benchmarks/dictionary_runtime_benchmark.py`
- `tests/test_experiment_dictionary.py`
- `tests/test_runtime_dictionary.py`
- `tests/test_runtime_state.py`
- `tests/test_dictionary_analysis.py`
- `docs/dictionary_optimization/implementation_plan.md`
- 五つの段階レポート
- 本レポート

## 実行した主なコマンド

```bash
.venv/bin/python src/dataset.py build-master \
  --input data/raw/JMdict_e.gz \
  --output data/master/master_dictionary.jsonl

.venv/bin/python src/experiment_dictionary.py \
  --master data/master/master_dictionary.jsonl \
  --sizes 100,200,500,1000,3000,5000,10000 \
  --seed 0 --min-length 2 --max-length 12 \
  --output data/dictionaries

.venv/bin/python src/experiment_dictionary.py \
  --master data/master/master_dictionary.jsonl \
  --size 10000 --seed 0 --min-length 2 \
  --max-lengths 3,4,5,6,8,10,12 \
  --output data/dictionaries

.venv/bin/python src/runtime_dictionary.py \
  --input data/dictionaries/D10000_L2-12_seed0.jsonl \
  --output data/runtime/D10000_L2-12_seed0.runtime.json

.venv/bin/python src/dictionary_analysis.py \
  --master data/master/master_dictionary.jsonl \
  --details data/dictionaries/D10000_L2-12_seed0.jsonl \
  --runtime data/runtime/D10000_L2-12_seed0.runtime.json \
  --output results/dictionary_analysis \
  --seed 0 --min-length 2 --max-length 12 \
  --comparison-size 10000 \
  --max-lengths 3,4,5,6,8,10,12 \
  --sizes 100,200,500,1000,3000,5000,10000

.venv/bin/python benchmarks/dictionary_runtime_benchmark.py \
  --details data/dictionaries/D10000_L2-12_seed0.jsonl \
  --text data/dictionaries/D10000_L2-12_seed0.txt \
  --runtime data/runtime/D10000_L2-12_seed0.runtime.json \
  --repetitions 1000 \
  --output data/runtime/D10000_L2-12_seed0.benchmark.json

.venv/bin/python -m py_compile src/*.py benchmarks/*.py
.venv/bin/python -m unittest discover -s tests -v
```

## 全テスト結果

- 自動テスト: 72件成功、失敗0
- 全Pythonファイルの構文検査: 成功
- マスター生成: 成功
- 実験辞書生成: 成功
- RuntimeDictionary生成・保存・再読込: 成功
- 辞書分析・CSV・PNG生成: 成功
- 旧AI小規模対局: 成功
- Runtime対局: 成功
- 人間入力状態確認: 成功

## マスター辞書

- entry数: 217,743
- 読み候補: 264,368
- 正規化成功: 246,780
- 正規化失敗: 17,588
- 統合後語数: 205,594
- 重複統合: 41,186
- 名詞候補: 178,672
- SHA256: `13f0e52aa4daca26a9e98ca85df70311d2aa34d2fc5c40891ba95cf90bbd7257`

名詞候補の優先度別語数:

- 高（3）: 16,768
- 中（2）: 6,876
- 低（1）: 155,028

マスター全体の主な文字数分布:

- 2文字: 2,277
- 3文字: 16,051
- 4文字: 38,433
- 5文字: 34,938
- 6文字: 33,071
- 7文字: 27,490
- 8文字: 19,780
- 9文字: 11,986
- 10文字: 7,197
- 11文字: 4,680
- 12文字: 3,118

現行`legacy_v1`の正規化内に2文字未満拒否が残っているため、一文字語620候補はマスターに入らない。

## 生成した実験用辞書

seed0、2〜12文字:

- D100、D200、D500、D1000、D3000、D5000、D10000

D10000、seed0:

- 最大3、4、5、6、8、10、12文字

各条件でTXT、詳細JSONL、metadata、statsを生成した。D10000 L2-12のTXT SHA256は`269db7918c542ca574d87d8d7e3d4f37ca57b5daa2bcb5d4cf93dcab649a730d`、詳細JSONL SHA256は`74273ec92dd5b9b50e5d125bf7fc94fc234d4603966a511f8ecb7898b44b9b29`である。

## 最大文字数ごとの候補語数

- 3以下: 15,883
- 4以下: 48,899
- 5以下: 77,845
- 6以下: 106,022
- 8以下: 147,894
- 10以下: 165,507
- 12以下: 172,713

全条件でD10000を生成できた。

## 辞書サイズ間の包含関係

D100⊂D200⊂D500⊂D1000⊂D3000⊂D5000⊂D10000を、読みのprefix比較で確認した。全比較行で`contains_previous_dictionary=True`だった。

## D10000実験辞書の文字数分布

- 2文字: 626
- 3文字: 2,305
- 4文字: 3,687
- 5文字: 1,783
- 6文字: 828
- 7文字: 437
- 8文字: 186
- 9文字: 75
- 10文字: 45
- 11文字: 20
- 12文字: 8

平均4.2786、中央値4、`ん`終端1,525語である。高優先度名詞候補だけでD10000を満たしたため、この辞書のpriority levelは全語3だった。

## RuntimeDictionaryの構造

- format: `runtime_dictionary_v1`
- word count: 10,000
- char count: 68
- `char_to_id/id_to_char`: ゲーム正規化後の安定文字ID
- `word_readings/word_to_id/word_lengths`
- `word_start_ids/word_end_ids`
- `initial_edge_counts`: 68×68の一次元配列
- `bucket_offsets/bucket_word_ids`: CSR単語バケット
- `initial_active_end_masks`: start IDごとのend IDビット集合

## グラフ統計

- 総辺数: 10,000
- 異なる辺種類数: 2,248
- 弱連結成分: 1、最大68
- 強連結成分: 3、最大66
- 最大出辺: `し`、686語
- 最大入辺: `ん`、1,525語
- 辞書サイズ別の異なる辺種類: 91、175、389、640、1,278、1,686、2,248

## AI対AI状態

`AIEdgeState`は次だけを保持する。

- `required_char_id`
- `edge_counts`
- `active_end_masks`
- `edge_history`

探索中は具体語を決めず、対局後に各辺のCSRバケットから異なるword IDを順番に割り当てる。apply/undoは対象辺と1ビットだけを変更する。

## 人間対AI状態

`HumanRuntimeState`は辺状態に次を追加する。

- `used_word_ids`
- `bucket_cursors`
- `word_history`

人間入力は共通正規化、辞書存在、使用済み、開始文字の順で検証する。AI具体語選択はcursorから走査し、人間が先に使った語をused setで飛ばす。

## 旧方式との一致確認

D10000の同じ読み一覧で次が一致した。

- 語順
- 総語数
- 開始文字別語数
- start/end別語数
- `ん`終端語数
- 移動可能end ID

word ID 0を一手使用した後、対象開始文字の残り語数は旧方式・新方式とも75だった。人間状態では`むとくてん`を一度受理し、二回目を`already_used`で拒否した。

D100のGreedy対Randomでは、旧対局とRuntime対局の両方が`winner=first`、1手、`no_legal_move`で終了した。

## 性能比較結果

D10000、1,000反復の参考値:

- 旧TXT辞書ロード: 0.007182秒
- Runtime JSONロード・全検証: 0.022216秒
- 詳細JSONLからRuntime構築: 0.077020秒
- 旧合法語列挙: 0.018764秒
- Runtime開始バケット取得: 0.001591秒
- 旧移動可能end列挙: 0.047200秒
- Runtime mask end列挙: 0.008558秒
- apply+undo: 0.000937秒
- edge countsコピー: 0.009127秒
- 旧used set（1,000語）コピー: 0.004150秒
- 新edge counts+maskコピー: 0.009327秒

概算メモリ:

- WordGraph: 2,470,489 bytes
- RuntimeDictionary: 2,038,564 bytes
- AI辺状態の可変部分: 41,656 bytes
- 人間状態の可変部分: 78,948 bytes
- 旧used set 1,000語: 60,984 bytes

Runtime JSONのロードは旧TXTより遅いが、合法語・end列挙は高速化した。状態全コピーは有利でないため、探索ではapply/undoを使う設計である。測定値はテスト合否には使用していない。

## 既存コードへ残した旧方式

- `dataset.parse_jmdict`と旧CSV生成
- `WordGraph`
- `agents.GameState(current_char, used_ids)`
- `match.simulate_match`
- `human_cli.py`の旧画面・対局ループ
- `exact_solver.py`のused mask完全解析
- 全既存AIの評価関数・探索処理

## 未解決の問題

- `legacy_v1`では一文字語を保持しない。
- 第二段階と第五段階は303MBマスターをPython objectとして読み、ピークメモリが大きい。
- Runtime JSONは可読性と全検証を優先しており、バイナリ形式よりロードが遅い。
- 既存AIアダプタは呼出時にword IDを一時復元する。探索自体はまだ辺ネイティブではない。
- D10000は全語が高優先度であり、中・低優先度を含む研究にはD拡大または別の抽出設計が必要。
- 図の日本語文字は実行環境のフォントに依存する。

## 簡略化した部分

- 固有名詞推定を行わず、`n-pr`専用派生項目を削除した。
- 古語、方言、専門語、俗語、まれな語を個別除外しない。
- 標準Pythonのlist、tuple、dict、intビット集合を使用した。
- NetworkX、NumPy等を追加しなかった。
- 人間CLIの画面は大規模変更せず、状態クラスと入力APIを独立追加した。

## 次に行うべきAI側の作業

1. 既存Greedy評価を辺数から直接計算するアダプタを作る。
2. Minimax/AlphaBetaの合法手をword IDではなくedge IDへ変更する。
3. apply/undoを探索再帰へ接続し、状態コピーを避ける。
4. 旧方式と辺ネイティブ方式の探索結果を小規模辞書で完全比較する。
5. その後に反復深化、置換表、手の並べ替えへ進む。

Minimax、AlphaBeta、MonteCarlo、Greedy、完全解析のアルゴリズム自体は今回変更していない。
