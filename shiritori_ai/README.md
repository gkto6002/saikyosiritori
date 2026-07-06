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

## 小規模完全解析

標準では小さすぎるDを外し、`D100, D150, D200, D250, D300` を `seed 0..4` で解析します。完全解析の標準タイムアウトは `120` 秒です。`--max-states` は未指定なら無制限で、基本的にタイムアウトまで探索します。

```bash
python src/experiments_exact.py \
  --jmdict data/raw/JMdict_e.gz \
  --sizes 100 150 200 250 300 \
  --seeds 0 1 2 3 4
```

主な出力:

- `results/exact/exact_runs.csv`: Dとseedごとの完全解析結果
- `results/exact/exact_summary_by_size.csv`: 辞書サイズごとの平均・標準偏差
- `results/exact/first_move_results.csv`: 初手ごとの勝敗
- `results/exact/char_stats.csv`: 文字ごとの統計
- `results/exact/dictionary_char_totals.csv`: 実験辞書そのものの先頭・終端文字合計

## 大規模近似AI対戦

標準では `D1000, D3000, D5000, D10000` を対象に、各AI組み合わせを1回ずつ対戦します。大きいDでも止まらないよう、1手ごとの時間制限、最大手数、試合全体の時間制限を分けて設定します。

```bash
python src/experiments_approx.py \
  --jmdict data/raw/JMdict_e.gz \
  --sizes 1000 3000 5000 10000 \
  --repetitions 1 \
  --time-limit-sec 4.0 \
  --max-match-time-sec 960
```

主な出力:

- `results/approx/matches.csv`: 各対戦の結果
- `results/approx/agent_summary.csv`: AIごとの集計
- `results/approx/match_logs.jsonl`: 手順履歴
- `results/approx/match_flow.csv`: 1手1行の読みやすい対戦手順
- `results/approx/match_flow.jsonl`: 対戦ごとの単語列と手順
- `results/approx/agent_end_char_stats.csv`: AI別・辞書サイズ別の終端文字統計
- `results/approx/first_player_by_size.csv`: Dごとの先手勝率
- `results/approx/top_end_chars.csv`: Dごとの上位頻出終端文字
- `results/approx/dictionary_char_totals.csv`: 実験辞書そのものの先頭・終端文字合計

打ち切り理由は `no_legal_move`、`ended_with_n`、`max_moves_reached`、`match_timeout` などで記録します。AIの1手制限超過は、各AIの `timeout_count` に記録します。

## 図の作成

```bash
python src/visualize.py
```

主な出力:

- `results/figures/exact_search_states_by_dict_size.png`
- `results/figures/exact_time_by_dict_size.png`
- `results/figures/exact_winning_first_moves_by_dict_size.png`
- `results/figures/exact_first_player_win_rate_by_dict_size.png`
- `results/figures/approx_agent_win_rate.png`
- `results/figures/approx_agent_avg_time.png`
- `results/figures/approx_agent_timeout_count.png`
- `results/figures/approx_first_player_win_rate_by_dict_size.png`
- `results/figures/approx_top_end_chars.png`
- `results/figures/approx_agent_win_rate_random_delta.png`: random除外によるAI別勝率差分
- `results/figures/approx_first_player_win_rate_random_delta.png`: random除外による先手勝率差分

## 人間対AI

```bash
python src/human_cli.py \
  --jmdict data/raw/JMdict_e.gz \
  --dict-size 1000 \
  --agent greedy \
  --human-first \
  --show-candidates
```

人間の入力は読み仮名で受け取り、辞書と同じ正規化を行います。不正な手は理由を表示して再入力を求めます。

## テスト

```bash
python -m unittest discover -s tests
```

## 注意点

- 完全解析はビットマスクで使用済み語集合を持つため、小規模辞書向けです。
- 大規模辞書では完全解析を行わず、近似AI対戦を使います。
- JMdict rawファイルは `.gitignore` 対象です。再現性は、取得URL、処理条件、seed、出力CSV/JSONで確保します。
