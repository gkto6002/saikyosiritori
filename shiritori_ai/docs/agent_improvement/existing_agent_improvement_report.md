# 既存探索AIの改善・検証・設定調整レポート

## 1. 結論

既存のMinimax、AlphaBeta、BeamNegamax、PVSを辺専用の状態表現のまま改善し、固定局面、同一深度、設定探索、D1000〜D20000の対局まで実行した。

- AlphaBetaのルートalpha共有は、選択手と評価値を90/90回維持したまま、深度4の固定局面で平均ノード数を1,795.1から471.3へ73.7%、平均時間を0.2306秒から0.0557秒へ75.8%削減した。
- PVSをAlphaBetaと同じ評価関数、候補集合、候補順序に揃えた。`aggressive_pvs`は後方互換名として残した。
- PVSの幅1.0のnull windowを`math.nextafter`へ変更した。90/90回で手と評価値が一致し、ノード数も増えなかったため採用した。
- 注意状態の簡易生存評価を候補依存にした。固定18局面では変更前後の選択辺は変わらず、勝敗への実測影響例は得られなかった。
- 同一深度D4の18対局はBeamNegamax 8勝、AlphaBeta 5勝、PVS 5勝だった。Beamの結果は深度差だけでは説明できない。
- seed 0・1の固定局面だけで最終設定を決め、seed 2を再調整に使わず確認した。
- 最終108対局ではAlphaBetaとPVSがともに35/48勝、BeamNegamaxが22/48勝、Minimaxが実施可能なD5000以下で16/24勝、Greedyが0/48勝だった。
- 内部タイムアウト、試合時間切れ、不正手、状態不整合は最終対局ではいずれも0件だった。

今回、置換表、Zobrist Hash、反復深化、LMR、アスピレーションウィンドウ、終盤完全解析、ハイブリッドAI、新しい探索エージェントは実装していない。

## 2. 変更前調査

変更前コミットは`1b4c28318343c046a50fd9d77d4ed7af6cea83aa`である。

### 探索設定

| AI | 標準深度 | 候補制限 |
|---|---:|---|
| Minimax | 3 | branch limit 12 |
| AlphaBeta | 3 | branch limit 12 |
| BeamNegamax | 4 | 幅12, 8, 4, 2 |
| AggressivePVS | 3 | branch limit 12 |

適応深度は一手中の反復深化ではない。現在深度を一回だけ探索し、ハードタイムアウトまたは制限時間の90%以上で次手の深度を一段下げる。50%以下で5手連続完了すると一段戻し、80%以上90%未満では回復カウントを進めない。

再帰中はハードdeadlineを`SearchTimeout`で伝播する。ソフトタイムアウトはルート候補間で次候補へ進むかを判定する。`apply_edge`後の探索は`finally`で`undo_edge`される構造だった。

### 評価と順序付け

候補順序は全候補へ軽量な攻撃評価を行い、即時勝利、即時敗北、評価値、文字IDの安定キーで整列していた。探索末端の評価は危険度に応じて攻撃評価と生存評価を合成していた。

危険度は現在手番の安全単語数と安全辺種類数から`normal`、`caution`、`danger`、`critical`へ分類する。変更前は設定上の`normal_survival_weight`が0.15だった一方、辺評価のnormal分岐は生存評価を実行せず攻撃評価だけを返しており、設定と実動作が不一致だった。

### 発見した実装上の問題

1. AlphaBetaは各ルート候補を毎回最大窓で探索し、前候補のalphaを次候補へ共有していなかった。
2. 辺ネイティブ探索の`aggressive_ordering=True`は、順序評価の`total_score`が攻撃評価そのものだったため、通常順序と実質同じだった。
3. 注意状態の簡易生存評価は、候補適用前の自分の集計値を使っており、同じ局面の全候補へ同じ値を足す可能性があった。
4. PVSの浮動小数点評価に幅1.0のnull windowを使っており、必要以上に広かった。
5. 一手ログには探索カウンタは存在したが、選択手の攻撃・生存内訳、相手と自分の集計値、全ルート候補数が不足していた。

変更前結果は`results/existing_agent_improvement/before`へ保存した。固定局面はD20000のseed 0、1、2から各6局面、合計18局面を採取した。内訳はnormal 9、caution 3、danger 3、critical 3で、各AIを各局面5回探索させた。

## 3. 実装内容

### AlphaBeta

最初のルート候補を通常窓で探索し、そのscoreで`root_alpha`を更新する。二候補目以降は子ノード側の窓を`[-WIN_SCORE, -root_alpha]`にして共有する。比較用に`share_root_alpha=False`も内部オプションとして残した。

単語状態と辺状態の両方で同じ修正を行った。タイムアウトを含め、辺適用後は必ず`finally`で取消す。

### PVS

公平な比較用の`PVSAgent`を明示し、AlphaBetaと同じ評価、候補集合、候補順序を使用する。既存CLI名`aggressive_pvs`と`AggressivePVSAgent`は同じ実装の後方互換別名として残した。

最初の候補は通常窓、二候補目以降はnull windowで探索する。値がalphaを上回りbeta未満のときだけ通常窓で再探索し、beta以上なら再探索せず枝刈りする。null window上端は既定で`math.nextafter(alpha, math.inf)`を使う。

### 注意状態の簡易生存評価

候補辺を適用した後、相手が到達できる安全な終端文字だけをビットマスクから列挙する。それぞれについて、自分が次に利用できる安全単語数、安全辺種類数、安全終端文字種類数を`AIEdgeState`の集計値から取得し、最悪値と小さな平均項を合成する。

全辺・全単語の走査は行わない。normalでは攻撃評価だけ、cautionではこの簡易評価、dangerとcriticalでは既存の完全生存評価を使う。即時勝敗の優先順位は変更していない。実動作に合わせ`normal_survival_weight`を0.0へ統一した。

### 分析ログ

既存のログ形式を維持し、`decision_extra`と対局フローへ次を追加した。

- risk level、attack、survival、survival weight、total score
- 相手の合法・安全単語数、全・安全辺種類数、全・安全終端文字種類数
- 自分の安全単語数、安全辺種類数、安全終端文字種類数
- root candidate count、searched root candidate count
- 既存のeffective depth、next depth、elapsed ratio、timed out

### 再実行と集計

`src/run_existing_agent_improvement.py`へ`--quick`、`--full`と段階別`--stage`を実装した。段階は`positions`、`benchmark`、`equal-depth`、`tuning`、`beam-retention`、`final`、`report`である。

manifestにはコミットID、設定ハッシュ、未コミット変更を含むPythonソースfingerprintを記録する。最終対局は一局ごとにJSON/CSVをcheckpointし、中断後は完了済みの辞書・先後・AI組を飛ばす。

## 4. AlphaBeta変更前後

同じ18局面、5反復、深度4、候補12、時間制限1秒で旧ルート最大窓と新ルートalpha共有を直接比較した。

| 方式 | 平均時間 | 平均ノード | タイムアウト率 |
|---|---:|---:|---:|
| 各候補を最大窓 | 0.230571秒 | 1,795.06 | 0% |
| ルートalpha共有 | 0.055721秒 | 471.33 | 0% |
| 変化 | -75.8% | -73.7% | 変化なし |

選択手一致率は100%（90/90）、評価値一致率も100%（90/90）だった。平均時間は約4.14倍、平均ノードは約3.81倍の改善である。

変更前と変更後の標準設定ベンチマーク全体を比較すると、AlphaBetaの平均時間は0.038065秒から0.018056秒、平均ノードは343.94から151.33へ減った。ただし、この値には注意評価など同時変更の影響も含むため、上表の隔離比較を主要結果とする。

## 5. PVS検証

幅1.0と`nextafter`を同じ90探索で比較した。

| null window | 平均時間 | 平均ノード | 再探索率 |
|---|---:|---:|---:|
| 幅1.0 | 0.055998秒 | 463.89 | 1.184% |
| `nextafter` | 0.055492秒 | 463.67 | 1.185% |

選択手と評価値は90/90回一致したため`nextafter`を採用した。

同一深度固定局面ではAlphaBetaとPVSの選択手が90/90回一致した。PVSの平均ノードは463.67でAlphaBetaの471.33より1.6%少なく、平均時間も0.048873秒対0.049287秒で0.8%短かった。一方、最終設定D5/B8ではPVSの固定局面時間とノードがAlphaBetaより多く、最終対局の一手平均もPVS 0.091951秒、AlphaBeta 0.082735秒だった。したがってPVSが常に速いとは結論できない。

## 6. 同一深度比較

固定条件はAlphaBeta D4/B12、BeamNegamax D4/幅12-8-4-2、PVS D4/B12、適応深度なし、各局面1秒である。

| AI | 平均時間 | 中央値 | p95 | 平均ノード | タイムアウト率 |
|---|---:|---:|---:|---:|---:|
| AlphaBeta | 0.049287秒 | 0.036916秒 | 0.115996秒 | 471.33 | 0% |
| BeamNegamax | 0.075143秒 | 0.080693秒 | 0.181069秒 | 830.00 | 0% |
| PVS | 0.048873秒 | 0.042508秒 | 0.085465秒 | 463.67 | 0% |

D20000、3 seed、全先後18対局の結果は次のとおりだった。

| AI | 勝数 |
|---|---:|
| AlphaBeta | 5 |
| BeamNegamax | 8 |
| PVS | 5 |

全18局が`ended_with_n`で終了し、内部タイムアウトは0だった。先手が16/18勝した。この比較では三手法の深度は同じであるため、BeamNegamaxの8勝は深度差だけではなく、深さごとの候補制限が作る探索経路・選択の差による。ただし18局だけなので一般的な強さの断定には不足する。

## 7. 設定探索

設定決定にはseed 0・1の固定局面だけを使用し、各条件を5回測定した。AlphaBeta/PVSは深度3、4、5と候補8、12、16、Beamは指定された4構成を測定した。タイムアウト、完了ルート数、p95、実効深度、選択安定性で候補を評価し、深く読めて安定し、同程度なら速い構成を選んだ。

| AI | 選択設定 | 平均時間 | 中央値 | p95 | 平均ノード | 完了ルート | 安定率 |
|---|---|---:|---:|---:|---:|---:|---:|
| AlphaBeta | D5/B8 | 0.071932秒 | 0.078222秒 | 0.143970秒 | 687.08 | 6.67 | 100% |
| BeamNegamax | D5/8-6-4-2 | 0.091600秒 | 0.096125秒 | 0.187078秒 | 1,048.92 | 6.67 | 100% |
| PVS | D5/B8 | 0.073567秒 | 0.080844秒 | 0.154247秒 | 737.08 | 6.67 | 100% |

三設定とも固定局面のタイムアウト率は0%、実効深度は設定どおり5だった。選択済み設定はseed 0・1の最終対局で確認した後も変更せず、seed 2へ適用した。

設定探索では全22構成を固定局面で一次選別したが、各残存構成どうしの完全な対局総当たりは実行していない。最終設定三つのseed 0・1対局を対局評価とした。これは今回の実行時間を抑えるための簡略化で、設定ごとの勝率まで厳密に最適化する場合の残課題である。

## 8. Beam参照手保持率

十分広いAlphaBeta D5/B16を参照し、Beamの軽量候補順序で参照手の順位を測定した。

| 危険度 | 局面数 | 同一手 | top 2 | top 4 | top 8 | top 12 | top 16 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 全体 | 18 | 77.8% | 88.9% | 88.9% | 88.9% | 88.9% | 100% |
| normal | 9 | 77.8% | 77.8% | 77.8% | 77.8% | 77.8% | 100% |
| caution | 3 | 33.3% | 100% | 100% | 100% | 100% | 100% |
| danger | 3 | 100% | 100% | 100% | 100% | 100% | 100% |
| critical | 3 | 100% | 100% | 100% | 100% | 100% | 100% |

幅12でも参照手を落とす2局面はいずれもnormalで、幅16なら全参照手を保持した。cautionでは候補上位には残るが、深い探索後の選択が参照手と異なる局面が多かった。局面ごとの順位、参照score、Beam選択、score差は`beam_retention_positions.csv`へ保存した。

反実仮想の対局を各局面から最後まで再生していないため、参照手落ちの勝敗影響は`unknown`である。今回は指示どおり動的ビーム幅を実装せず、normal局面で幅16へ広げる案を後続候補に残す。

## 9. 注意状態修正の影響

攻撃評価が同じで生存可能性だけが異なるテスト局面では、安全に戻れる候補へ高い簡易生存scoreが付くことを確認した。normalで生存評価0回、cautionで簡易評価だけ1回、danger/criticalで完全評価だけ1回になることもテストした。

変更前後の固定18局面では、AlphaBeta、Beam、PVSの代表選択辺はすべて一致した。そのため、この固定集合では選択手が変わった具体例も勝敗が変わった具体例も存在しない。修正は「候補間で差が付かない」不具合を除いたが、勝率への影響を主張できるサンプルは今回得られなかった。

## 10. 最終対局

利用可能だった辞書はD1000、D3000、D5000、D10000のseed 0と、D20000のseed 0、1、2だった。存在しないseedの辞書は新規生成していない。MinimaxはD5000以下だけ実行した。各AI組は先後を入れ替えた。

### AI別全体

| AI | 対局 | 勝 | 勝率 | 一手平均時間 | 内部timeout |
|---|---:|---:|---:|---:|---:|
| AlphaBeta | 48 | 35 | 72.9% | 0.082735秒 | 0 |
| BeamNegamax | 48 | 22 | 45.8% | 0.074480秒 | 0 |
| Greedy | 48 | 0 | 0.0% | 0.000236秒 | 0 |
| Minimax | 24 | 16 | 66.7% | 0.025470秒 | 0 |
| PVS | 48 | 35 | 72.9% | 0.091951秒 | 0 |

AlphaBetaとPVSは今回の対戦集合で同じ35勝となった。Greedyを含むため全体勝率は探索AI側へ大きく寄っており、AI間の純粋な順位はサイズ別・pairwise CSVも併読する必要がある。

### 辞書サイズ別勝率

| D | seed | AlphaBeta | Beam | PVS | Minimax |
|---:|---|---:|---:|---:|---:|
| 1000 | 0 | 62.5% | 62.5% | 62.5% | 62.5% |
| 3000 | 0 | 50.0% | 75.0% | 50.0% | 75.0% |
| 5000 | 0 | 75.0% | 37.5% | 75.0% | 62.5% |
| 10000 | 0 | 83.3% | 33.3% | 83.3% | 未実施 |
| 20000 | 0,1,2 | 83.3% | 33.3% | 83.3% | 未実施 |

各セルの対局数は小さい。D3000ではBeamとMinimax、D5000以上ではAlphaBetaとPVSが上位になったが、この結果だけで辞書サイズによる一般的な順位変化を断定しない。

### seed 2の独立確認

D20000では各seed 12局を実行した。

| seed | 平均手数 | 先手勝率 | AlphaBeta | Beam | PVS |
|---:|---:|---:|---:|---:|---:|
| 0 | 144.58 | 41.7% | 5/6 | 2/6 | 5/6 |
| 1 | 151.42 | 41.7% | 5/6 | 2/6 | 5/6 |
| 2 | 150.25 | 41.7% | 5/6 | 2/6 | 5/6 |

seed 2の勝敗構成はseed 0・1と一致し、平均手数は両者の範囲内だった。この結果を見た後の設定変更は行っていない。

### 先手効果と終了理由

最終108局では先手49勝、後手59勝で、先手勝率は45.4%だった。終了理由は`no_legal_move` 59局、`ended_with_n` 49局である。一方、同一深度の三探索AIだけでは先手16/18勝だった。対戦集合とエージェントの組合せに強く依存し、今回の全体結果から一律の先手有利は確認できない。

辞書seed別の全体平均手数は、seed 0が54.40、seed 1が151.42、seed 2が150.25だが、seed 0には小規模辞書84局が混在する。seed比較には上表のD20000同士を使うべきである。

## 11. 各AIの特徴

| 観点 | Minimax | AlphaBeta | BeamNegamax | PVS |
|---|---|---|---|---|
| 探索の正確性 | 候補・深度内は素直 | 候補・深度内で正確 | ビーム外を捨てる近似 | AlphaBetaと同じ手を高率で再現 |
| 速度 | 枝刈りなしで大Dに弱い | ルート共有後は安定 | 固定幅で計算量を制御 | 条件によりABより僅かに少ノード |
| 深く読む能力 | 辞書拡大で急速に悪化 | D5/B8が安定 | D5を安定して使えた | D5/B8が安定 |
| 候補見落とし | branch limit由来 | branch limit由来 | ビーム落ちが追加で存在 | branch limit由来 |
| 危険局面 | 共通完全生存評価 | 共通完全生存評価 | 今回の危険・瀕死で参照手保持100% | 共通完全生存評価 |
| 終盤 | 小局面なら読める | 枝刈りが有効 | 強制手を保持すれば速い | 良い順序で狭窓が有効 |
| 大辞書耐性 | D5000までに限定 | 良好 | 計算量は制御しやすい | 良好だが今回はABより一手時間が長い |

ハイブリッドAIへ引き継ぐ価値がある要素は、AlphaBetaの安定した完全窓探索、PVSの低い再探索率、Beamの深度確保能力、危険度別生存評価、辺数とビットマスクによる高速集計である。後続では、normalで参照手が落ちる場合だけ候補幅を増やす判断、終盤完全解析への安全な切替、置換表と反復深化を独立に検証する価値がある。

## 12. テストと実行コマンド

主な実行コマンド:

```bash
.venv/bin/python -m unittest discover -s tests

.venv/bin/python src/run_existing_agent_improvement.py --quick --force
.venv/bin/python src/run_existing_agent_improvement.py --full --stage benchmark --force
.venv/bin/python src/run_existing_agent_improvement.py --full --stage equal-depth --force
.venv/bin/python src/run_existing_agent_improvement.py --full --stage tuning --force
.venv/bin/python src/run_existing_agent_improvement.py --full --stage beam-retention --force
.venv/bin/python src/run_existing_agent_improvement.py --full --stage final --force
.venv/bin/python src/run_existing_agent_improvement.py --full --stage report --force

.venv/bin/python src/experiments_approx.py \
  --runtime \
    data/dictionaries/D20000_L2-12_seed0.runtime.json \
    data/dictionaries/D20000_L2-12_seed1.runtime.json \
    data/dictionaries/D20000_L2-12_seed2.runtime.json \
  --agents alpha_beta beam_negamax pvs \
  --repetitions 1 \
  --time-limit-sec 1.0 \
  --max-moves 1000 \
  --max-match-time-sec 300 \
  --alpha-beta-depth 4 \
  --beam-negamax-depth 4 \
  --aggressive-pvs-depth 4 \
  --branch-limit 12 \
  --beam-widths 12,8,4,2 \
  --no-adaptive-depth \
  --output-dir results/existing_agent_improvement/equal_depth/matches
```

追加・更新したテストは、ルートalpha共有、手とscoreの一致、ノード非増加、状態復元、PVSの公平な順序と浮動小数点窓、AB/PVS小規模一致、危険度別の評価切替、候補依存の注意評価、必須ログ、CLI別名、full設定格子、CSV集計、ソースfingerprint、最終対局集計を対象とする。

最終テスト結果は、`115 tests / OK`である。

## 13. 変更ファイル

変更:

- `README.md`
- `src/agents.py`
- `src/search_common.py`
- `src/match.py`
- `src/experiments_approx.py`
- `src/human_cli.py`
- `tests/test_search_agents.py`

追加:

- `benchmarks/existing_agents_benchmark.py`
- `src/run_existing_agent_improvement.py`
- `src/existing_agent_analysis.py`
- `tests/test_existing_agent_improvement.py`
- `docs/agent_improvement/existing_agent_improvement_report.md`
- `results/existing_agent_improvement`以下の今回専用結果

既存の未追跡ファイルと過去の結果は削除・上書きしていない。

## 14. 成果物

- 変更前: `results/existing_agent_improvement/before`
- 修正後固定局面・方式比較: `results/existing_agent_improvement/after`
- 同一深度: `results/existing_agent_improvement/equal_depth`
- 設定探索: `results/existing_agent_improvement/tuning`
- Beam保持率: `results/existing_agent_improvement/beam_retention`
- 最終対局: `results/existing_agent_improvement/final`
- 集計JSON/CSV: `results/existing_agent_improvement/analysis`
- グラフ9枚: `results/existing_agent_improvement/figures`
- 自動要約: `results/existing_agent_improvement/automated_report.md`

## 15. 未解決事項

1. 設定候補すべての対局総当たりは未実施で、固定局面による一次選別と選択後のseed 0・1対局に簡略化した。
2. Beamが参照手を落とした局面の反実仮想勝敗は未確定である。
3. 注意評価修正で選択手や勝敗が変わる実データ局面は今回の固定18局面では観測されなかった。
4. D1000〜D10000はseed 0しか存在せず、サイズ別順位はseed差と分離できない。
5. D10000とD20000ではMinimaxを実行時間上の理由で除外した。
6. 時間測定は実行環境の揺れを含む。正しさの合否には使わず、5反復の中央値とp95を併記した。
7. 今回禁止された置換表、反復深化、終盤完全解析、ハイブリッド化は次工程で個別に導入・比較する必要がある。
