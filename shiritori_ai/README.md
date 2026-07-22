# 有限辞書しりとりにおける勝敗解析AIと大規模辞書用近似AI

JMdictから生成した有限辞書上で、日本語しりとりをゲームとして解析するPythonプロジェクトです。小規模辞書ではメモ化再帰による完全解析を行い、大規模辞書ではランダム、貪欲、深さ制限ミニマックス、モンテカルロAIを対戦させます。

## 実行環境

- Python 3.10以上
- 図の作成には `matplotlib`
- CSV、JSON、XML処理は標準ライブラリ中心

```bash
python -m pip install -r requirements.txt
```

## JMdictの取得

JMdict rawファイルはサイズが大きく日次更新されるため、Git管理対象から外しています。次のコマンドで取得します。

```bash
python src/dataset.py download --output data/raw/JMdict_e.gz
```

JMdict/EDICTはEDRDGにより提供され、CC BY-SA 4.0で利用できます。出典とライセンスの詳細は `data/SOURCE.md` に記載しています。

## 辞書生成

JMdictから読みを抽出し、2文字以上12文字以下のひらがな読みだけを残します。`ke_pri` と `re_pri` から優先度を付け、標準では高優先度語を最大限優先して固定seedでD語を抽出します。`--pool-multiplier` を2以上にすると、優先度を保ちつつ候補プールを広げられます。

```bash
python src/dataset.py build \
  --jmdict data/raw/JMdict_e.gz \
  --dict-size 1000 \
  --random-seed 0 \
  --output data/generated/D1000_seed0.csv \
  --metadata-output data/generated/D1000_seed0_metadata.json
```

動作確認用CSVも使えますが、本実験はJMdict由来データを使ってください。

### 最適化済み実験辞書と辺データ

情報保持型マスター辞書から実験辞書を生成する場合は、次を実行します。実験辞書と同時に、探索用`RuntimeDictionary`と人が内容を確認するためのCSVも生成されます。JMdict XMLを第二段階以降で再解析することはありません。

```bash
python src/experiment_dictionary.py \
  --master data/master/master_dictionary.jsonl \
  --size 10000 \
  --seed 0 \
  --min-length 2 \
  --max-length 12 \
  --output data/dictionaries
```

`D10000_L2-12_seed0`の場合、主な出力は次のとおりです。

- `.txt`: 既存AI向けの一行一語形式
- `.jsonl`: 優先度や出典entry IDを持つ詳細単語形式
- `.words.csv`: word ID、読み、長さ、開始・終了文字と文字ID、所属辺の語数
- `.edges.csv`: 非空の`開始文字→終了文字`ごとの語数、word ID一覧、単語一覧
- `.runtime.json`: 辺数、CSR単語バケット、active end maskを持つ探索用形式
- `.metadata.json`、`.stats.json`: 生成条件、各ファイルのSHA256、辞書・辺統計

単語単位では`.words.csv`、有向多重グラフの辺単位では`.edges.csv`を表計算ソフトなどで開くと確認できます。辺CSVの`words`と`word_ids`は、CSVセル内のJSON配列です。`を`などの遷移文字は既存ゲーム規則に従い正規化された値が`start_char`・`end_char`へ入ります。

## 小規模完全解析

完全解析も単語やword IDを使わず、文字IDと辺の多重度だけを使用します。各辺の使用回数は混合基数の一つの整数へ符号化し、`(required_char_id, edge_usage_code)`をメモ化キーにします。勝ち初手辺を一つ発見した時点で、そのDの解析を終了します。生成済み辞書を解析する場合、文字数条件を再指定する必要はありません。

```bash
python src/experiments_exact.py \
  --runtime data/dictionaries/D100_L2-12_seed0.runtime.json \
  --timeout-sec 120 \
  --output-dir results/exact_edge_D100
```

最大の生成済みRuntimeDictionaryを使い、Dを増加させて最初のタイムアウトまで測る場合は次を実行します。RuntimeDictionary内の共通語彙順位の先頭D語を使うため、文字数条件やseedを再入力しません。

```bash
python src/experiments_exact.py \
  --runtime-prefix data/dictionaries/D10000_L2-12_seed0.runtime.json \
  --size-start 100 \
  --size-step 50 \
  --timeout-sec 120 \
  --output-dir results/exact_growth
```

`--max-size`で上限を指定できます。複数seedの最大RuntimeDictionaryを`--runtime-prefix`へ列挙した場合は、同じDで全seedがタイムアウトした時点で停止します。`--sizes 100 200 500`を加えると自動増加ではなく指定Dだけを解析します。

複数の完成済み辞書そのものを解析する場合は`--runtime`の後へ明示的に列挙します。旧`--jmdict`／`--records`入力も互換用に残し、その場合もD100から50ずつ増やして全seedがタイムアウトするまで解析できます。どの入力でも完全解析へ渡す時点では`EdgeDictionary`だけになります。

主な出力:

- `results/exact/exact_runs.csv`: Dとseedごとの完全解析結果
- `results/exact/exact_summary_by_size.csv`: 辞書サイズごとの平均・標準偏差
- `results/exact/first_move_results.csv`: 勝ち辺発見までに調べた初手辺の勝敗、start/end ID、辺の多重度
- `results/exact/char_stats.csv`: 文字ごとの統計
- `results/exact/dictionary_char_totals.csv`: 実験辞書そのものの先頭・終端文字合計

`exact_runs.csv`の`decision_status`は`win_found`、`loss_proven`、`timeout`のいずれかです。`decision_status=win_found`かつ`first_move_scan_complete=false`の場合、`winning_first_move_count`と`losing_first_move_count`は勝ち辺発見までの調査済み部分だけの値です。`timeout`では勝敗と両件数を未確定として空欄にします。

## 大規模近似AI対戦

標準では `D1000, D3000, D5000, D10000` を対象に、各AI組み合わせを1回ずつ対戦します。AI対AIでは単語やword IDを状態へ持たず、文字ID、辺の残数、active end maskだけを使用します。Random、Greedy、Minimax、MonteCarlo、AlphaBetaはすべて辺を直接選択します。自己対戦は勝敗統計の偏りになるため生成しません。大きいDでも止まらないよう、1手ごとの時間制限、最大手数、試合全体の時間制限を分けて設定します。

```bash
python src/experiments_approx.py \
  --runtime data/dictionaries/D10000_L2-12_seed0.runtime.json \
  --agents greedy alpha_beta \
  --time-limit-sec 4.0 \
  --max-match-time-sec 960
```

複数の生成済み辞書は`--runtime`の後へ明示的に列挙できます。辞書サイズ、seed、文字数条件は隣接metadataから取得するため再指定しません。旧`--runtime-dir`、`--records`、`--jmdict`入力も互換用に残していますが、AI探索は同じ辺専用経路で実行されます。

`--repetitions` は `random` または `monte_carlo` を含む対戦だけに適用します。`greedy`、`minimax`、`alpha_beta` だけの決定的な対戦は同じ辞書上で繰り返しても同じフローになるため、1回だけ実行します。集計では同じ `(D, seed, first_agent, second_agent)` の反復を1つの対戦単位に平均化し、反復したAIだけが勝率や先手勝率で重くならないようにします。

主な出力:

- `results/approx/matches.csv`: 各対戦の結果
- `results/approx/agent_summary.csv`: AIごとの集計
- `results/approx/match_logs.jsonl`: 手順履歴
- `results/approx/match_flow.csv`: 1手1行の開始・終了文字ID、辺番号、使用前後の辺数
- `results/approx/match_flow.jsonl`: 対戦ごとの辺列と手順
- `results/approx/agent_end_char_stats.csv`: AI別・辞書サイズ別の終端文字統計
- `results/approx/first_player_by_size.csv`: Dごとの先手勝率
- `results/approx/top_end_chars.csv`: Dごとの上位頻出終端文字
- `results/approx/dictionary_char_totals.csv`: 実験辞書そのものの先頭・終端文字合計

打ち切り理由は `no_legal_move`、`ended_with_n`、`max_moves_reached`、`match_timeout` などで記録します。AIの1手制限超過は、各AIの `timeout_count` に記録します。

近似AIは `random`、`greedy`、`minimax`、`monte_carlo`、`alpha_beta` を指定できます。`minimax` と `alpha_beta` は、1手でタイムアウトしたら以後の探索深さを1下げ、タイムアウトしない手が3回続いたら1戻す適応depthを使います。標準depthは `minimax=3`、`alpha_beta=4` です。`alpha_beta` は `minimax` と同じ評価関数を使い、alpha-beta pruning で不要な枝を刈ります。

## 図の作成

```bash
python src/visualize.py
```

主な出力:

- `results/figures/exact_search_states_by_dict_size.png`
- `results/figures/exact_time_by_dict_size.png`
- `results/figures/exact_winning_first_moves_by_dict_size.png`
- `results/figures/exact_first_player_win_rate_by_dict_size.png`
- `results/figures/exact_completion_by_dict_size.png`
- `results/figures/approx_agent_win_rate_including_random.png`: randomを含む対戦でのAI別勝率
- `results/figures/approx_agent_win_rate_excluding_random.png`: randomを除く対戦でのAI別勝率
- `results/figures/approx_first_player_win_rate_including_random.png`: randomを含む対戦での先手勝率
- `results/figures/approx_first_player_win_rate_excluding_random.png`: randomを除く対戦での先手勝率
- `results/figures/approx_d10000_pairwise_agent_results.png`: `D10000` の先手AI対後手AIの先手勝率行列
- `results/figures/approx_agent_avg_time_per_move.png`
- `results/figures/approx_agent_timeouts_per_match.png`
- `results/figures/approx_top_end_chars.png`

## 人間対AI

```bash
python src/human_cli.py \
  --runtime data/dictionaries/D1000_L2-12_seed0.runtime.json \
  --agent greedy \
  --human-first \
  --show-candidates
```

人間対AIだけは具体語の重複判定と画面表示が必要なため、`HumanRuntimeState`がword IDを保持します。AIの思考中はコピーした辺専用状態だけを渡し、AIが辺を確定した後に、その辺の未使用単語を一語だけ割り当てて表示します。人間の入力は読み仮名で受け取り、辞書と同じ正規化を行います。不正な手は理由を表示して再入力を求めます。
人間対AIでは、AIの1手ごとの標準タイムアウトは `2.0` 秒です。

## テスト

```bash
python -m unittest discover -s tests
```

## 注意点

- 完全解析は辺使用回数を一意な整数へ符号化しますが、状態数自体は指数的に増えるため小規模辞書向けです。
- 大規模辞書では完全解析を行わず、近似AI対戦を使います。
- JMdict rawファイルは `.gitignore` 対象です。再現性は、取得URL、処理条件、seed、出力CSV/JSONで確保します。
