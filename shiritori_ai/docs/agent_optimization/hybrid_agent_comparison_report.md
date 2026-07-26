# ハイブリッドエージェント実装・D10000比較レポート

## 実装概要

既存の辺数ベース探索を維持し、次の3エージェントを追加した。

- `graph_pvs`: 軽量GraphControl特徴による候補順序付けとPVS
- `beam_alpha_beta`: ply別Beam幅による候補制限とAlphaBeta
- `beam_pvs`: ply別Beam幅による候補制限とPVS

既存の候補生成、評価関数、`AIEdgeState.apply_edge` / `undo_edge`、
タイムアウト、適応深度、探索統計を再利用した。既存の
`AlphaBetaAgent`、`PVSAgent`、`BeamNegamaxAgent`、
`GraphControlAgent`の挙動は変更していない。

GraphPVSで全候補のSCCを全探索ノードで再計算すると高コストになるため、
既存GraphControlのうち、相手の残存語数、安全語数、出辺種類、2手到達範囲、
低出次数・行き止まり率、行先集中度を使う軽量orderingを採用した。

Beam系は固定`branch_limit`を使用せず、`8,6,4,2`のような幅を
探索plyごとに適用する。候補制限後、BeamAlphaBetaは通常のAlphaBeta窓、
BeamPVSは最初の候補を通常窓、以降をnull windowで探索する。

## 変更・追加ファイル

主な変更:

- `src/agents.py`
- `src/graph_control.py`
- `src/search_common.py`
- `src/match.py`
- `src/experiments_approx.py`
- `src/human_cli.py`
- `src/run_graph_control_comparison.py`
- `src/run_search_parameter_tuning.py`
- `src/analyze_graph_control_comparison.py`
- `src/visualize.py`
- `README.md`

追加:

- `src/run_hybrid_agent_benchmark.py`
- `src/analyze_hybrid_comparison.py`
- `tests/test_hybrid_agents.py`

## 追加統計

- Beamのply別候補総数、選択数、呼出回数、最大選択数
- Beamによる除外候補数
- AlphaBeta/PVS cutoff数
- PVS null-window探索数、再探索数、再探索率
- Graph ordering評価数、呼出回数、先頭候補変更回数、所要時間
- 実効深度、深度変更回数

## テスト

次を追加確認した。

- 3ハイブリッドが合法辺を返す
- 同じseedと状態で再現可能
- タイムアウト後に状態が完全に戻る
- 適応深度を有効化できる
- Beam幅をどのplyでも超えない
- Graph orderingがPVSの探索順へ実際に反映される
- factory、AI対AI CLI、人間対AI CLIから生成できる
- 固定局面ベンチマークと対局集計が新規エージェントを扱える

全自動テスト結果は175件成功、失敗0件。

## D10000実験条件

- 辞書サイズ: 10000
- 辞書seed: 0、1、2
- エージェント: AlphaBeta、PVS、BeamNegamax、GraphControl、
  GraphPVS、BeamAlphaBeta、BeamPVS
- 各決定的組合せ: 1回
- 先後: 入替あり
- 総試合数: 126
- 1手制限: 1.0秒
- 最大手数: 1000
- 試合全体上限: 300秒
- 適応深度: 無効
- 探索深度: 5
- AlphaBeta/PVS/GraphPVS候補上限: 8
- Beam幅: 8、6、4、2
- 候補単位: 有向辺種類、多重度は辺残数で管理

## 同一深度・固定局面結果

深度5、14局面の結果:

| agent | 平均秒 | p95秒 | 平均ノード | timeout | 勝手完了 |
|---|---:|---:|---:|---:|---:|
| AlphaBeta | 0.1631 | 0.2397 | 1881.6 | 0 | 100% |
| PVS | 0.1372 | 0.2250 | 1605.1 | 0 | 100% |
| BeamNegamax | 0.0917 | 0.1191 | 1350.0 | 0 | 100% |
| GraphControl | 0.2065 | 0.9154 | 0.0 | 0 | 100% |
| GraphPVS | 0.3202 | 0.6649 | 1655.6 | 0 | 100% |
| BeamAlphaBeta | 0.0265 | 0.0410 | 403.9 | 0 | 100% |
| BeamPVS | 0.0299 | 0.0421 | 443.0 | 0 | 100% |

同一深度での変化:

- GraphPVS / PVS: 時間+133.4%、ノード+3.2%
- BeamAlphaBeta / Beam: 時間-71.1%、ノード-70.1%
- BeamAlphaBeta / AlphaBeta: 時間-83.8%、ノード-78.5%
- BeamPVS / Beam: 時間-67.4%、ノード-67.2%
- BeamPVS / PVS: 時間-78.2%、ノード-72.4%

BeamAlphaBetaとBeamNegamaxは14/14局面で選択手と評価値が一致した。
BeamPVSとBeamNegamaxも14/14局面で一致した。したがって、この固定局面では
AlphaBeta/PVS枝刈りが結果を変えず、不要な探索だけを削減した。

GraphPVSとPVSの選択手一致は10/14局面だった。Graph orderingは探索ノードの
先頭候補を14.1%の呼出で変更したが、ノード数を減らせなかった。
Graph ordering単体で平均0.1750秒を使用した。

## D10000対局結果

| agent | W-L-D | 勝率 | 先手勝率 | 後手勝率 | 平均秒 | 平均ノード | timeout |
|---|---:|---:|---:|---:|---:|---:|---:|
| AlphaBeta | 26-10-0 | 72.2% | 72.2% | 72.2% | 0.1278 | 1231.6 | 0 |
| PVS | 27-9-0 | 75.0% | 72.2% | 77.8% | 0.1310 | 1285.4 | 0 |
| BeamNegamax | 22-14-0 | 61.1% | 77.8% | 44.4% | 0.0970 | 1224.9 | 0 |
| GraphControl | 0-36-0 | 0.0% | 0.0% | 0.0% | 0.0312 | 0.0 | 12 |
| GraphPVS | 8-28-0 | 22.2% | 22.2% | 22.2% | 0.3666 | 1542.4 | 50 |
| BeamAlphaBeta | 22-14-0 | 61.1% | 77.8% | 44.4% | 0.0234 | 281.2 | 0 |
| BeamPVS | 21-15-0 | 58.3% | 72.2% | 44.4% | 0.0279 | 343.9 | 0 |

主要な直接対戦:

- AlphaBeta対PVS: 3-3
- AlphaBeta対BeamAlphaBeta: 4-2
- PVS対BeamPVS: 4-2
- BeamNegamax対BeamAlphaBeta: 3-3
- BeamNegamax対BeamPVS: 3-3
- BeamAlphaBeta対BeamPVS: 3-3
- PVS対GraphPVS: 6-0
- BeamAlphaBeta対GraphPVS: 6-0

## 同一時間枠での深度確認

深度6:

| agent | 平均秒 | p95秒 | timeout |
|---|---:|---:|---:|
| AlphaBeta | 0.8009 | 1.0001 | 42.9% |
| PVS | 0.7394 | 1.0001 | 7.1% |
| BeamNegamax | 0.3136 | 0.3740 | 0% |
| BeamAlphaBeta | 0.0760 | 0.1082 | 0% |
| BeamPVS | 0.0790 | 0.1385 | 0% |

深度7:

| agent | 平均秒 | p95秒 | timeout |
|---|---:|---:|---:|
| BeamNegamax | 0.3744 | 0.4829 | 0% |
| BeamAlphaBeta | 0.1905 | 0.3491 | 0% |
| BeamPVS | 0.1872 | 0.4054 | 0% |

BeamAlphaBetaとBeamPVSはD7でも全局面を1秒以内に完了した。通常AlphaBetaは
D6で6/14局面、PVSは1/14局面がタイムアウトした。Beamとの組合せにより、
同じ時間制限で2段階ほど深い探索を実行できる余地が確認できた。

## 3方式の評価

### GraphControl + PVS

悪化した。Graph orderingは候補順を変更したがcutoff効率を改善せず、
固定局面ではPVSより2.33倍遅く、対局では50回タイムアウトした。
対局勝率もPVSの75.0%から22.2%へ低下した。原因は、軽量グラフ特徴の
計算コストと、その順位が現在の評価関数・PVS窓に適した順序ではないこと。

### Beam + AlphaBeta

最も明確な成功。純Beamと同じ勝率61.1%、直接対戦3-3、固定局面の手も
14/14一致したまま、対局平均判断時間を0.0970秒から0.0234秒へ約75.9%
短縮し、平均ノードを1224.9から281.2へ約77.0%削減した。

ただしD5の勝率自体はAlphaBetaの72.2%より低い。高速化分を深度6または7へ
使う追加対局に価値がある。

### Beam + PVS

純Beamより平均判断時間を約71.3%、平均ノードを約71.9%削減した。
固定局面では純Beamと14/14一致したが、全対局勝率は58.3%で純Beamより
2.8ポイント低かった。対局中の再探索率は5.1%で、通常PVSの1.3%より高い。
狭いBeam内では最初の候補が十分強くなく、null-window再探索の相対コストが
増えたと考えられる。

## 結論と次の改善

現時点の主力候補はBeamAlphaBetaである。D5では純Beamと強さを維持しながら
約4倍高速で、D7も1秒以内に安定して完了した。

次に試す価値が高い順:

1. BeamAlphaBeta D6・D7のD10000対局
2. Beam幅`12,8,4,2`と`8,6,4,2`の比較
3. BeamPVSのroot ordering改善による再探索率低下
4. GraphPVSは全ノード適用をやめ、rootのみ、または上位候補のtie-breakだけに限定
5. Graph ordering特徴の個別ablation

既存単体手法は削除せず、すべて従来名と設定で利用可能な状態を維持している。

## 適応深度ありの次段階比較

D10000の次段階では、探索深度を持たない`graph_control`単体を比較対象から
外す。既存手法は`results/search_parameter_tuning/f5a877380b91`で採用した
`aggressive`設定を流用する。

| agent | 初期深度 | 最大深度 | その他 |
|---|---:|---:|---|
| AlphaBeta | 5 | 7 | branch 8 |
| PVS | 5 | 7 | branch 8 |
| BeamNegamax | 6 | 8 | beam 8-6-4-2 |
| GraphPVS | 4 | 5 | branch 8 |
| BeamAlphaBeta | 7 | 8 | beam 8-6-4-2 |
| BeamPVS | 7 | 8 | beam 8-6-4-2 |

全手法で1手上限1.0秒、目標時間0.6秒、深度低下閾値0.95、
回復閾値0.6、回復待ち2手、深度増減幅1を使う。

GraphPVSは固定D5対局で50回タイムアウトしたため、初期深度を4へ下げ、
最大深度を既測定の5に制限した。BeamAlphaBetaとBeamPVSは保存14局面の
D7でタイムアウトがなく、p95もそれぞれ0.3491秒、0.4054秒だったため、
初期深度7・最大深度8とした。最大深度8は未測定なので、適応制御によって
重い局面では自動的に深度を戻す前提である。

実行コマンド:

```bash
.venv/bin/python -u src/run_graph_control_comparison.py \
  --full \
  --adaptive-depth \
  --sizes 10000 \
  --seeds 0,1,2 \
  --time-limit-sec 1.0
```

6手法、3辞書seed、全順序対戦で合計90局となる。従来の固定深度比較は
`--adaptive-depth`を付けなければ同じ設定で再実行できる。
