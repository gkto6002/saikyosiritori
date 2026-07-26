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

複数seedを同じ条件でまとめて生成するときは`--seed`の代わりに`--seeds`を使います。マスター辞書は一度だけ読み込まれ、各seedの実験辞書・単語CSV・辺CSV・RuntimeDictionaryが同時に生成されます。

```bash
.venv/bin/python src/experiment_dictionary.py \
  --master data/master/master_dictionary.jsonl \
  --size 50000 \
  --seeds 0,1,2 \
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

標準では `D1000, D3000, D5000, D10000` を対象に、各AI組み合わせを1回ずつ対戦します。AI対AIでは単語やword IDを状態へ持たず、文字ID、辺の残数、active end maskだけを使用します。Random、Greedy、Minimax、MonteCarlo、AlphaBeta、BeamNegamax、AggressivePVSはすべて辺を直接選択します。自己対戦は勝敗統計の偏りになるため生成しません。大きいDでも止まらないよう、1手ごとの時間制限、最大手数、試合全体の時間制限を分けて設定します。

```bash
python src/experiments_approx.py \
  --runtime data/dictionaries/D10000_L2-12_seed0.runtime.json \
  --agents greedy alpha_beta \
  --time-limit-sec 4.0 \
  --max-match-time-sec 960
```

複数の生成済み辞書は`--runtime`の後へ明示的に列挙できます。辞書サイズ、seed、文字数条件は隣接metadataから取得するため再指定しません。旧`--runtime-dir`、`--records`、`--jmdict`入力も互換用に残していますが、AI探索は同じ辺専用経路で実行されます。

`--repetitions` は `random` または `monte_carlo` を含む対戦だけに適用します。`greedy`、`minimax`、`alpha_beta` だけの決定的な対戦は同じ辞書上で繰り返しても同じフローになるため、1回だけ実行します。集計では同じ `(D, seed, first_agent, second_agent)` の反復を1つの対戦単位に平均化し、反復したAIだけが勝率や先手勝率で重くならないようにします。

D50000をseed 0・1・2で全AI比較する例は次のとおりです。`--repetitions 3`の場合、各seedで決定的な対戦は1回、RandomまたはMonteCarloを含む対戦は3回実行され、7 AIでは1 seedあたり86対局、3 seed合計258対局です。

```bash
.venv/bin/python src/experiments_approx.py \
  --runtime \
    data/dictionaries/D50000_L2-12_seed0.runtime.json \
    data/dictionaries/D50000_L2-12_seed1.runtime.json \
    data/dictionaries/D50000_L2-12_seed2.runtime.json \
  --agents random greedy minimax monte_carlo alpha_beta beam_negamax aggressive_pvs \
  --repetitions 3 \
  --time-limit-sec 1.0 \
  --max-moves 100 \
  --max-match-time-sec 120 \
  --output-dir results/approx_D50000_seeds0-2_r3
```

### 共通評価関数

候補手と探索深度到達局面は、共通の次式で評価します。

```text
score = attack_score + survival_weight * survival_score
```

`attack_score`は相手の合法単語数、安全単語数、安全辺種類数、安全な終端文字種類数を少なくする手を高く評価し、`ん`辺の多さを小さく加点します。候補順序付けではこの軽量な攻撃評価だけを使います。探索末端では、通常状態は攻撃評価のみ、注意状態は現在の集計値による簡易生存評価、危険・瀕死状態だけは相手の各安全応手後の最悪値を調べる完全生存評価を使います。

辺ネイティブ評価の生存重みは通常`0.0`、注意`0.35`、危険`0.8`、瀕死`1.5`です。安全単語数の閾値は`10 / 5 / 2`、安全辺種類数は`3 / 2 / 1`で、係数と閾値は`EvaluationConfig`に集約しています。開始文字ごとの単語数、辺種類数、終端文字マスクは`AIEdgeState`が保持し、辺の適用・取消時に差分更新します。

### 探索系AI

- `minimax`: 標準深度3、候補上限12。
- `alpha_beta`: 標準深度3、候補上限12でalpha-beta枝刈りを行います。
- `full_alpha_beta`: 標準深度3。候補上限を設けず、全合法辺を対象にalpha-beta枝刈りを行います。
- `beam_negamax`: 標準深度4。深さごとに`12,8,4,2`辺へ候補を制限するNegamaxで、alpha-beta枝刈りは行いません。
- `pvs`: 標準深度3、候補上限12。AlphaBetaと同じ候補集合・評価・順序を使い、最初の候補を通常窓、2本目以降を浮動小数点用null windowで探索し、必要な場合だけ通常窓で再探索します。
- `aggressive_pvs`: 既存コマンドを壊さないために残した`pvs`の後方互換名です。
- `graph_pvs`: GraphControlの軽量グラフ特徴で全探索ノードの候補を並べ、PVSを行います。
- `beam_alpha_beta`: 深さ別Beam幅で候補を制限し、その集合へAlphaBeta枝刈りを行います。D10000追試で採用した標準設定は初期深度8・最大深度9・幅`12,8,4,2`です。
- `beam_pvs`: 深さ別Beam幅で候補を制限し、その集合へPVSを行います。標準設定は初期深度8・最大深度9・幅`12,8,4,2`です。

これらの探索系AIは、1手中の反復深化を行いません。現在の`current_depth`を1回探索します。ハードタイムアウトまたは制限時間の90%以上を使うと次手の深度を1下げ、50%以下で5回連続完了すると1戻します。80%以上90%未満では回復回数を増やしません。再帰中の時間切れは`SearchTimeout`で上位へ伝播し、`apply_edge`後は`finally`で必ず`undo_edge`します。

```bash
python src/experiments_approx.py \
  --runtime data/dictionaries/D10000_L2-12_seed0.runtime.json \
  --agents alpha_beta beam_negamax aggressive_pvs \
  --branch-limit 12 \
  --beam-widths 12,8,4,2 \
  --time-limit-sec 4.0 \
  --max-match-time-sec 960
```

`--branch-limit`はMinimax、AlphaBeta、PVSへ適用され、標準は12です。候補全体を軽量評価した後、上位候補だけを探索するため、即時勝利辺は上限外へ落ちません。MonteCarloは候補を1本ずつラウンドロビンで試行し、候補間の試行数差を原則1以内に保ちます。

固定局面の一手性能は`benchmarks/edge_search_benchmark.py`で計測できます。D20000・3 seedでの高速化前後の結果と対局スモークは`docs/agent_optimization/edge_native_search_performance_report.md`に記録しています。

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

各手の`decision_extra`に、`nodes_searched`、`leaf_evaluations`、`completed_root_moves`、`effective_depth`、`next_depth`、`timed_out`を保存します。AlphaBeta/PVSは`cutoff_count`と`pruned_move_count`、BeamNegamaxは`beam_pruned_move_count`、PVSはnull windowと再探索回数も記録します。

### 既存探索AIの改善実験

固定局面、同一深度比較、設定探索、Beam参照手保持率、最終対局、集計と図の作成は一つのランナーから再実行できます。`--quick`は配線確認、`--full`は本実験です。`--stage`には`positions`、`benchmark`、`equal-depth`、`tuning`、`beam-retention`、`final`、`report`を指定できます。中間結果のmanifestにはコミットID、設定ハッシュ、未コミット変更を含むソースfingerprintを保存します。

```bash
.venv/bin/python src/run_existing_agent_improvement.py --quick
.venv/bin/python src/run_existing_agent_improvement.py --full
.venv/bin/python src/run_existing_agent_improvement.py --full --stage report
```

本実験のレポートは`docs/agent_improvement/existing_agent_improvement_report.md`、機械可読な集計は`results/existing_agent_improvement/analysis`、図は`results/existing_agent_improvement/figures`にあります。

### 既存AIの詳細特徴分析

既存108局を重複させず再利用し、必要な全手ログ、主要AI直接対決、探索効率、Beam参照手保持、反実仮想、危険度、辞書構造、代表対局を分析します。`--quick`は配線確認、`--full`は108局のトレースと全Beam局面を対象とします。

```bash
.venv/bin/python src/run_existing_agent_analysis.py --quick
.venv/bin/python src/run_existing_agent_analysis.py --full
.venv/bin/python src/run_existing_agent_analysis.py --full --stage beam-analysis
```

詳細レポートは`docs/agent_analysis/existing_agent_detailed_analysis.md`、HybridAgentの設計案は`docs/agent_analysis/hybrid_agent_design_proposal.md`、JSON・CSV・図・代表対局は`results/existing_agent_analysis`に保存されます。この分析は既存AIの探索処理と評価関数を変更しません。

### GraphControlAgentと全AI比較

`GraphControlAgent`はゲーム木探索やランダムプレイアウトを行わず、候補辺を
一時適用した残存多重有向グラフを一手評価する決定論的AIです。AI対AIでは
具体語を保持せず、候補も`start_id → end_id`と残存多重度で記録します。
具体語の割当は人間対AIの表示時だけ行います。

quickはD1000 seed 0でGraphControlと全AIを先後入替し、fullは
D1000、D3000、D5000、D10000、D20000のseed 0、1、2で全8 AIの
全組合せを実行します。決定論同士は1回、RandomまたはMonteCarloを含む
組合せは5回です。fullの一手制限1秒、探索深度・分岐制限・Beam幅は既存の
最終比較設定を維持します。

```bash
python src/run_graph_control_comparison.py --quick
python src/analyze_graph_control_comparison.py \
  --input results/agent_comparison/quick/<run-hash> \
  --reference-positions 100 \
  --reference-time-limit-sec 0.2

python src/run_graph_control_comparison.py --full
python src/analyze_graph_control_comparison.py \
  --input results/agent_comparison/full/<run-hash> \
  --reference-positions 500 \
  --reference-time-limit-sec 1.0
```

最初にD5000だけで全AIを選抜する場合は、次を使用します。3 seed、
全8 AI、先後入替、確率系5反復で480局です。

```bash
python src/run_graph_control_comparison.py \
  --full \
  --sizes 5000 \
  --seeds 0,1,2
```

最後に表示される`results/agent_comparison/D5000/<run-hash>`を集計へ渡します。

```bash
python src/analyze_graph_control_comparison.py \
  --input results/agent_comparison/D5000/<run-hash> \
  --reference-positions 100 \
  --reference-time-limit-sec 1.0
```

D5000の成績から選んだAIだけを大辞書で比較する例:

```bash
python src/run_graph_control_comparison.py \
  --full \
  --sizes 10000,20000 \
  --seeds 0,1,2 \
  --agents alpha_beta,pvs,beam_negamax,graph_control
```

各runはコミットID、未コミット変更を含むソース指紋、実験設定ハッシュ、
辞書ハッシュを保存します。同じ条件の完了済み対局だけを再利用し、対局ごとに
JSON Linesへ追記するため途中再開できます。通常対局ログとGraphControlの
全候補詳細ログは別ファイルです。集計CSV/JSON、30種類のPNG、自動レポートは
各runの`analysis`以下へ保存されます。

## AlphaBeta・PVS・Beamのパラメータ調整

D5000の実対局から固定局面を作り、固定深度の選別、適応深度の閾値比較、
最終対局、値付き図表、レポートまで順番に実行します。

```bash
python src/run_search_parameter_tuning.py --full
```

短時間の動作確認には`--quick`、段階実行には
`--stage positions|fixed|adaptive|matches|analysis`を使用します。出力は
`results/search_parameter_tuning/<run-hash>/`へ保存され、同一runの完了済み
探索と対局は再利用されます。同じrunを同時実行するとロックエラーで停止します。
適応深度の再実験だけを行う場合は、互換性を検証したうえで既存runの固定深度結果を
`--reuse-fixed-from <run-dir>`により再利用できます。
別の辞書サイズへ移る場合は`--dictionary-size`と`--selection-from`を使用します。
選定済みの初期深度・枝数・Beam幅だけを引き継ぎ、新しい辞書上で固定設定と
適応プロファイルを再測定します。対局ID、manifest、CSV、図表には新しい辞書サイズが
保存されます。

```bash
python src/run_search_parameter_tuning.py \
  --full \
  --stage adaptive \
  --dictionary-size 50000 \
  --selection-from results/search_parameter_tuning/<D5000-run> \
  --max-moves 3000 \
  --max-match-time-sec 600
```

大規模辞書では、最初から全seed・全54対局を実行せず、seed 0の主要12対局を
パイロットとして実行できます。`--match-limit`はそのコマンドで新しく実行する
対局数だけを制限し、完了済み対局は数えません。これらは実行順の指定なので、
同じrunを後から別seedやfull計画へ拡張できます。

```bash
python src/run_search_parameter_tuning.py \
  --full \
  --stage matches \
  --dictionary-size 50000 \
  --selection-from results/search_parameter_tuning/<D5000-run> \
  --resume-run results/search_parameter_tuning/<D50000-run> \
  --match-plan pilot \
  --match-seeds 0 \
  --match-limit 3 \
  --max-moves 3000 \
  --max-match-time-sec 600
```

通常の対局CLIでも、初期深度から上昇できる最大深度増分と、深度調整に使う
通常目標時間を指定できます。`--time-limit-sec`は絶対上限であり、
`--target-time-sec`を超える傾向では深度を下げ、十分軽い手が続けば
`--adaptive-max-depth-increment`の範囲で深度を上げます。

```bash
python src/experiments_approx.py \
  --runtime data/dictionaries/D5000_L2-12_seed0.runtime.json \
  --agents alpha_beta pvs beam_negamax \
  --adaptive-depth \
  --adaptive-max-depth-increment 2 \
  --target-time-sec 0.4 \
  --depth-decrease-ratio 0.9 \
  --depth-recovery-ratio 0.5 \
  --depth-recovery-turns 3 \
  --depth-step 1
```

最大深度増分を省略すると0、通常目標時間を省略するとハード制限時間となり、
以前と同じ「初期深度が最大深度」の動作を維持します。
`--no-timeout-decreases-depth`を指定すると、ハードタイムアウト自体を深度低下の
条件にしません。ただし、同時に処理時間比が低下閾値以上なら時間比を理由として
深度が下がります。

## Full AlphaBetaと上位候補制限版の比較

既存の`alpha_beta`は`--branch-limit`で評価上位候補だけを探索する
Selective AlphaBetaです。`full_alpha_beta`は各plyの全合法辺を対象にし、
候補数による近似を行わず、AlphaBetaの値に基づく枝刈りだけを使用します。
どちらも固定深度の場合、探索深度より先は同じ評価関数で推定するため、
`full_alpha_beta`は完全解析ではありません。

まず、パラメータ調整で保存した同一局面を使い、Fullと上位8・12・16制限を
深度3・4・5で比較します。Fullがルート全候補を時間内に完了した局面だけを
手と評価値の参照比較に使用します。

```bash
python src/run_full_alpha_beta_comparison.py \
  --positions results/search_parameter_tuning/<D10000-run>/fixed_positions.json \
  --stage benchmark \
  --depths 3 4 5 \
  --branch-limits 8 12 16 \
  --time-limit-sec 1.0
```

出力先は`results/full_alpha_beta_comparison/<run-hash>/`です。固定局面ごとの
JSON Lines・CSV、設定別集計、Full完了率、Fullとの手・評価値一致率、
値付きグラフ、`report.md`を保存します。完了済み局面は再利用できます。

固定局面の結果から対局可能な深度を選んだ後、Fullと上位8制限を先後入替で
比較します。最初のコマンドで表示されたrunを`--resume-run`へ渡します。

```bash
python src/run_full_alpha_beta_comparison.py \
  --positions results/search_parameter_tuning/<D10000-run>/fixed_positions.json \
  --stage matches \
  --depths 3 4 5 \
  --branch-limits 8 12 16 \
  --time-limit-sec 1.0 \
  --match-depth 4 \
  --match-branch-limit 8 \
  --match-seeds 0 1 2 \
  --max-moves 3000 \
  --max-match-time-sec 600 \
  --resume-run results/full_alpha_beta_comparison/<run-hash>
```

通常の近似対局と人間対AIでも`full_alpha_beta`を選択できます。ただし、
大辞書の序盤は合法辺種類が非常に多いため、深度5で全候補を完了できるとは
限りません。

## 3種類のハイブリッド探索

`graph_pvs`、`beam_alpha_beta`、`beam_pvs`は既存の辺状態、評価関数、
apply/undo、タイムアウト、適応深度、探索統計を共有します。GraphPVSは
全候補でSCCを再計算せず、GraphControlの残存語数、出辺種類、2手到達範囲、
低出次数・行き止まり率、行先集中度を軽量orderingとして全探索ノードへ
適用します。Beam系は固定branch limitではなく、`--beam-widths`の値を
探索plyごとに使います。

D10000の保存局面を使った同一深度比較:

```bash
.venv/bin/python -u src/run_hybrid_agent_benchmark.py \
  --positions results/search_parameter_tuning/f5a877380b91/fixed_positions.json \
  --depth 5 \
  --branch-limit 8 \
  --beam-widths 8,6,4,2 \
  --time-limit-sec 1.0
```

D10000・3辞書seed・先後入替の対局:

```bash
.venv/bin/python -u src/run_graph_control_comparison.py \
  --full \
  --sizes 10000 \
  --seeds 0,1,2 \
  --agents alpha_beta,pvs,beam_negamax,graph_control,graph_pvs,beam_alpha_beta,beam_pvs \
  --time-limit-sec 1.0
```

### Beamハイブリッドの深度・幅追試

AlphaBetaを基準に、BeamAlphaBetaとBeamPVSの現行、深度増加、幅増加、
深度と幅の同時増加を比較します。各変種はD10000のseed 0〜9で
AlphaBetaと先後入替し、合計160局です。

| 条件 | 初期深度 | 最大深度 | Beam幅 |
|---|---:|---:|---|
| baseline | 7 | 8 | 8,6,4,2 |
| deep | 8 | 9 | 8,6,4,2 |
| wide | 7 | 8 | 12,8,4,2 |
| deep_wide | 8 | 9 | 12,8,4,2 |

保存14局面では標準幅D9が両方式ともタイムアウト0だった一方、D10は
BeamAlphaBeta 7.1%、BeamPVS 42.9%がタイムアウトしました。そのため
深度増加条件の最大深度は9です。`12,8,6,4`はD8でもほぼ全件
タイムアウトしたため、本対局の幅増加には上位plyだけを広げる
`12,8,4,2`を採用します。

```bash
.venv/bin/python -u src/run_beam_hybrid_followup.py
```

同じコマンドで途中再開できます。最後に表示されたパスを分析へ渡します。

```bash
.venv/bin/python src/analyze_beam_hybrid_followup.py \
  --input results/beam_hybrid_followup/D10000/<run-hash>
```

分析では変種別・辞書seed別の勝率、先後別勝率、判断時間、探索ノード、
実効深度、タイムアウト率、PVS再探索率をJSON・CSV・値付きグラフへ保存します。

160局の追試では、`deep_wide`がAlphaBetaに対してBeamAlphaBeta 16勝4敗、
BeamPVS 14勝6敗で両方式の最良条件となりました。この結果を受け、
通常の`beam_alpha_beta`と`beam_pvs`の標準設定を初期深度8・最大深度9・
幅`12,8,4,2`へ更新しています。過去条件を比較する追試ランナー内の
`baseline`定義は再現性のため変更していません。

適応深度を有効にした次段階の比較では、`graph_control`単体を除外し、
既存手法はD10000のパラメータ調整で採用した`aggressive`設定を再利用します。
AlphaBeta/PVSは初期深度5・最大7、BeamNegamaxは初期6・最大8です。
新手法は実測時間を基に、GraphPVSを初期4・最大5、
BeamAlphaBeta/BeamPVSを初期8・最大9とします。全手法の目標時間は0.6秒、
低下閾値は目標時間比0.95、回復閾値は0.6、2手連続で回復です。

```bash
.venv/bin/python -u src/run_graph_control_comparison.py \
  --full \
  --adaptive-depth \
  --sizes 10000 \
  --seeds 0,1,2 \
  --time-limit-sec 1.0
```

この設定は6手法、3辞書seed、全組合せの先後入替で90局です。出力先は
`results/agent_comparison/D10000_adaptive/<run-hash>`になります。

対局後のハイブリッド専用集計:

```bash
.venv/bin/python src/analyze_hybrid_comparison.py \
  --input results/agent_comparison/D10000_adaptive/<run-hash> \
  --benchmark results/hybrid_agent_comparison/benchmark/821264dd868d
```

`--benchmark`には同じD10000保存14局面を深度5で測定した既存結果を渡します。
適応対局の実効深度は対局ログ側の`effective_depth`と`depth_change_count`で
別に集計されます。

BeamPVS、BeamAlphaBeta、AlphaBeta、PVSに絞って辞書seedを0〜9へ
増やす追試では、まず不足しているseed 3〜9の辞書を生成します。

```bash
.venv/bin/python src/experiment_dictionary.py \
  --master data/master/master_dictionary.jsonl \
  --size 10000 \
  --seeds 3,4,5,6,7,8,9 \
  --min-length 2 \
  --max-length 12 \
  --output data/dictionaries
```

続いて4手法、10seed、全組合せの先後入替を実行します。決定論的手法だけ
なので反復は行わず、合計120局です。

```bash
.venv/bin/python -u src/run_graph_control_comparison.py \
  --full \
  --adaptive-depth \
  --sizes 10000 \
  --seeds 0,1,2,3,4,5,6,7,8,9 \
  --agents alpha_beta,pvs,beam_alpha_beta,beam_pvs \
  --time-limit-sec 1.0
```

ログには既存項目に加え、Beamのply別候補総数・選択数・最大選択数、
Graph orderingの評価回数・先頭候補変更回数・所要時間を保存します。

## 盤面適応型ハイブリッド

第二段階の盤面適応型として、分岐数切替、動的Beam幅AlphaBeta/PVS、
PVS再探索適応、終盤完全解析、これらの統合型を追加しています。
既存AIの標準設定は変更していません。D10000本実験は、調整用seedと
最終評価用seedを分離した専用ランナーで実行します。

```bash
.venv/bin/python -u src/run_position_adaptive_hybrid_experiment.py \
  --stage tune
```

実験設計、再開方法、最終評価と集計の正確なコマンドは
[`docs/agent_optimization/position_adaptive_hybrid_report.md`](docs/agent_optimization/position_adaptive_hybrid_report.md)
を参照してください。人間対AI・通常の近似実験CLIでも、新6手法を
`--agent`で指定できます。

D10000・180局の実験では固定BeamAlphaBetaを上回る十分な証拠が得られず、
440局の追加評価は行わず完了としました。標準エージェントと設定は変更しません。
結果は
[`docs/agent_optimization/position_adaptive_hybrid_experiment_result.md`](docs/agent_optimization/position_adaptive_hybrid_experiment_result.md)
に記録しています。

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

BeamNegamaxまたはAggressivePVSと対戦する場合は、`--agent beam_negamax --beam-widths 12,8,4,2`または`--agent aggressive_pvs --aggressive-pvs-depth 3 --branch-limit 12`を指定します。

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
