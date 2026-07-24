# 既存AI詳細特徴分析

## 1、分析目的

AlphaBetaAgent、PVSAgent、BeamNegamaxAgent、MinimaxAgent、GreedyAgentについて、現在の勝敗、探索時間、判断傾向を既存結果と追加計測から説明し、後続のHybridAgent設計根拠を作る。

AIの評価関数、探索、候補順序、標準設定は変更していない。追加したのは分析スクリプトと結果に影響しない集計処理だけである。

## 2、使用したデータ

- `results/existing_agent_improvement/final/final_matches.json`: 最終108局
- `results/existing_agent_improvement/equal_depth`: 同一深度18局と固定18局面×5反復
- `results/existing_agent_improvement/beam_retention`: 固定局面の参照手保持率
- `results/existing_agent_improvement/tuning`: seed 0・1の設定探索
- `results/existing_agent_analysis/traces/final_match_traces.jsonl`: 今回追加した108局・8,216手の全手ログ
- 生成済みD1000、D3000、D5000、D10000、D20000 RuntimeDictionary

最終108局は`(runtime, first_agent, second_agent)`で108件すべて一意だった。必須の辞書サイズ、seed、先後、AI、勝者、手数、終了理由も全行に存在した。決定的AIの同一条件反復を独立対局として重複集計していない。

元の最終結果には一手履歴がなかったため、同じRuntimeDictionary、最終設定、先後で108局を計測用に再実行した。勝者は108/108局で一致し、手数は107/108局で一致した。`D10000_seed0_greedy_vs_pvs`だけ元の37手に対し追加計測は63手だった。1秒のsoft deadline付近で完了ルート候補数が実行時間に左右された可能性があり、「時間制限付き探索は完全に同じ手順を保証する」という前提への反例である。勝敗は変わっていない。

元108局の内部timeoutは0件だったが、追加トレースでは8,216手中3手が1秒へ到達した。勝率の正本には元108局を使い、一手性能には追加ログを使う。

## 3、実験条件

最終設定はAlphaBeta D5/B8、PVS D5/B8、Beam D5/幅8-6-4-2で、適応深度なし、1手1秒である。MinimaxはD5000以下、Greedyは全サイズで実行した。

Beam参照手分析では、各実対局局面を復元し、AlphaBeta D5/B16が選ぶ手を「参照手」とした。これは完全解析による真の最善手ではない。1,582個のBeam手番を分析した。

反実仮想は、Beam敗戦で参照手がroot幅8外へ初めて落ちた局面を一局一箇所選び、Beam実手を参照手へ置き換え、その後を元と同じAI設定で最後まで再対局した。一手置換は因果の証明ではない。

## 4、対戦成績の再分析

基準値は既存結果と一致した。

| 対戦 | 成績 |
|---|---:|
| AlphaBeta対PVS | 7勝7敗 |
| AlphaBeta対Beam | 12勝2敗 |
| PVS対Beam | 12勝2敗 |

AlphaBeta対BeamではAlphaBetaが先手時5/7、後手時7/7。PVS対Beamも同じだった。AlphaBeta対PVSは互いに先手3/7、後手4/7で対称だった。

全体勝率72.9%にはGreedy戦が含まれる。主要AI間の評価では、AlphaBeta/PVSがBeamへ12勝2敗した直接対決を優先する。同一深度18局でBeamが8勝した事実だけからBeamが最強とはいえない。

## 5、先手と後手の影響

全108局の先手勝率は49/108、45.4%で、後手勝率54.6%だった。

| D | 先手勝率 |
|---:|---:|
| 1000 | 40.0% |
| 3000 | 45.0% |
| 5000 | 60.0% |
| 10000 | 41.7% |
| 20000 | 41.7% |

AI別ではAlphaBetaとPVSが先手66.7%、後手79.2%、Beamが先手37.5%、後手54.2%、Minimaxが両方66.7%、Greedyが両方0%だった。対戦相手の構成が同一でないMinimaxと他AIを単純比較しない。

同一辞書・seed・AI組を先後二局で組にした分類は`matchups/paired_seats.csv`へ保存した。AlphaBeta/PVS対Beamでは、強い側が先後とも勝つ組が多く、先後より手法差の方が大きかった。

## 6、辞書サイズとseedの影響

既存結果のサイズ別順位を再確認した。

| D | 上位 |
|---:|---|
| 1000 | AlphaBeta、PVS、Beam、Minimaxが62.5% |
| 3000 | Beam、Minimaxが75.0% |
| 5000 | AlphaBeta、PVSが75.0% |
| 10000 | AlphaBeta、PVSが83.3% |
| 20000 | AlphaBeta、PVSが83.3% |

各セルは少数対局であり、D3000のBeam優位だけを一般化できない。MinimaxはD5000以下だけなので、全辞書を含む主要AIグラフから分離した。

D20000の平均手数はseed 0が144.58、seed 1が151.42、seed 2が150.25だった。AI別勝敗は各seedでAlphaBeta 5/6、PVS 5/6、Beam 2/6と一致した。

辞書構造ではD20000の非空辺種類数がseed 0/1/2で2,895/2,897/2,892、安全語数が16,954/16,966/16,937だった。差は小さく、seed 1・2が長い理由を単一の構造量で説明できない。

7辞書だけの記述的相関では総語数と平均手数が`r=0.991`、安全辺種類数と平均手数が`r=0.940`だった。サイズ増加で利用可能な循環経路が増え、長期化する説明とは整合する。ただし辞書サイズと各構造量が同時に増えるため、独立した因果効果ではない。

## 7、AlphaBetaとPVSの探索効率

同一深度固定局面では選択手90/90、評価値90/90で一致した。

| 指標 | AlphaBeta | PVS |
|---|---:|---:|
| 固定局面平均時間 | 0.04929秒 | 0.04887秒 |
| 固定局面平均nodes | 471.33 | 463.67 |
| 固定局面p95時間 | 0.1160秒 | 0.0855秒 |
| 実対局平均時間 | 0.13294秒 | 0.14246秒 |
| 実対局中央値 | 0.11552秒 | 0.11754秒 |
| 実対局p95 | 0.31386秒 | 0.34256秒 |
| 実対局平均nodes | 1,143.0 | 1,295.4 |
| 実対局中央値nodes | 998 | 1,072 |
| 実対局p95 nodes | 2,468 | 3,047 |
| 一node当たり時間 | 116.3µs | 110.0µs |

PVSの実対局null-windowは1,918,107回、再探索は23,935回、再探索率1.248%だった。固定局面の約1.09%と近い。

再探索なし188手は平均298.8 nodes、0.0356秒、再探索あり2,015手は平均1,388.4 nodes、0.1524秒だった。ただし再探索ありは平均候補数54.0、なし31.8であり、差を再探索だけの追加コストとはみなせない。

実対局でPVSはAlphaBetaより一node当たり6%ほど軽い一方、node削減が起きず、総nodesが13.3%多いため総時間も7.2%長かった。狭窓管理のPython負荷より、局面と深度5での再探索・枝刈り経路によるnode増加が主要説明である。

PVSはAlphaBetaより強い別AIではなく、同じ評価・候補・順序を別の窓制御で探索する方式として扱うべきである。今回の最終設定では単純で速いAlphaBetaを基礎にする方が合理的である。

## 8、各AIの判断傾向

全対局経路の単純平均では、AlphaBeta/PVSが相手へ残した安全語数は約83.8、Beamは111.8だった。ただし対局経路が異なるため、この平均だけでは判断傾向を証明しない。

Beam実手とAlphaBeta参照手を同じ1,582局面で直接比較した。812局面で手が異なり、その局面ではBeam実手が参照手より相手へ残す安全語数が平均28.9語、安全辺種類数が5.27種類多く、attack scoreは平均676.4低かった。Beamが相手の選択肢を早く減らす仮説は支持されない。

AlphaBetaとPVSは固定局面の全危険度で100%一致したため、共通傾向として扱える。Beamとの差はnormal局面で最も大きく、near-deathでは固定・実対局とも一致率が高かった。

ログの`own_safe_*`は選択前の現在手番集計であり、選択後に相手応手を経た自分の将来手数そのものではない。この値から「自分の安全手を残した」と直接断定しない。

## 9、Beamの参照手保持分析

### 固定18局面

top 2〜12が88.9%、top 16が100%だった。

### 実対局1,582局面

| 幅 | 参照手保持率 |
|---:|---:|
| 2 | 68.2% |
| 4 | 80.2% |
| 6 | 90.3% |
| 8 | 95.1% |
| 12 | 99.1% |
| 16 | 100% |

幅8外は78局面だった。危険度別top 8はnormal 93.9%、caution/danger/near-death 100%である。問題は主に候補の多いnormal局面に集中した。

参照手が幅8内にあってもBeam実手との一致率は全体48.7%だった。したがってroot候補削減だけでなく、深さごとの8-6-4-2縮小、近似探索、同点処理を含む探索経路が選択差を生む。

## 10、Beamの敗因分析

主要AIへのBeam敗戦24局を機械的に分類した。

- 20局: 最初の敗着候補で参照手がroot幅8外
- 4局: 参照手は幅内だが別手を選択。深層ビーム幅または近似探索が候補

これは敗因の確定ではなく、数値根拠を伴う仮説分類である。軽量評価と完全なゲーム価値の順位差、深層のどこで参照経路が消えたかは現在のログだけでは完全に分離できない。

Beamの勝利時平均は52.14手、敗北時平均は119.42手だった。勝利22局のうち100手以上は4.5%、敗北26局では53.8%である。Beamは短い対局で勝ちやすく、長期戦で弱い仮説を支持する。

## 11、反実仮想分析

幅8外へ参照手が落ちた敗戦20局へ一手置換を行った。

| 分類 | 件数 |
|---|---:|
| 敗北から勝利へ改善 | 5 |
| 勝敗同じ・長く生存 | 12 |
| 勝敗不変 | 3 |
| 悪化 | 0 |

改善例:

- D3000 Beam対AlphaBeta、25手目、参照順位10
- D3000 Beam対PVS、25手目、参照順位10
- D10000 Beam対AlphaBeta、35手目、参照順位10
- D10000 Beam対PVS、35手目、参照順位10
- D20000 seed 0 Beam対AlphaBeta、3手目、参照順位12

この結果は候補削減が勝敗へ影響しうる具体例だが、一手だけ変えた後は両AIが新しい経路を選ぶため、元局面の唯一の敗因を証明するものではない。

## 12、危険度別分析

追加8,216手ではnormalが大半だった。主要AIの危険局面はnormalより候補が少なく、思考時間・nodesも小さかった。

固定局面のAlphaBeta/PVS一致率はnormal、caution、danger、near-deathすべて100%。Beamとの一致率はnormal 100%、caution 66.7%、danger 66.7%、near-death 100%だった。ただし固定normalは採取局面であり、実対局Beam参照手一致率43.5%とは母集団が異なる。

実対局のBeam top 8参照手保持率:

- normal: 93.9%
- caution: 100%
- danger: 100%
- near-death: 100%

注意状態は445手あった。全445手で候補間のsurvival scoreに差が生じ、静的なattack 1位と`attack + survival` 1位が変わったのは3手だった。3手では実際の選択もsurvival込み1位と一致し、いずれも最終的に勝利した。論理修正が実際の候補順位へ影響する例は確認できたが、修正前を同一対局で再実行していないため、勝敗改善を因果的には主張しない。

## 13、対局手数と終盤性能

| AI | 平均 | 中央値 | p95 | 最短 | 最長 |
|---|---:|---:|---:|---:|---:|
| AlphaBeta | 91.35 | 59 | 285 | 4 | 321 |
| PVS | 91.35 | 59 | 285 | 4 | 321 |
| Beam | 88.58 | 61 | 215 | 4 | 285 |
| Minimax | 43.88 | 44 | 72 | 4 | 90 |
| Greedy | 48.02 | 37 | 100 | 4 | 105 |

MinimaxはD5000以下だけなので、手数が短いことを終盤能力の差とはみなさない。

終盤は対局全体の後半3分の1と定義した。AlphaBeta/PVSは同一の対局結果と手数分布を持ち、長期戦でも安定した。Beamは敗北時だけ長期化し、参照手との差がnormalの早期・中盤で積み重なった後に危険局面へ入る傾向がある。

辞書サイズ増加に伴い平均手数はD1000 20.8、D3000 40.8、D5000 42.9、D10000 62.1、D20000 148.8へ増えた。

## 14、代表対局

自動抽出結果:

- AlphaBetaがBeamに勝利: `D1000_seed0_beam_negamax_vs_alpha_beta`
- BeamがAlphaBetaに勝利: `D1000_seed0_alpha_beta_vs_beam_negamax`
- AlphaBeta/PVS比較: `D1000_seed0_alpha_beta_vs_pvs`
- Beamが参照手を落とす: `D10000_seed0_alpha_beta_vs_beam_negamax`
- 反実仮想で勝敗変化: `D3000_seed0_beam_negamax_vs_alpha_beta`
- 危険状態から勝利: `D1000_seed0_alpha_beta_vs_beam_negamax`
- 最長: `D20000_seed2_alpha_beta_vs_pvs`
- 最短: `D1000_seed0_greedy_vs_alpha_beta`

全手順と、各対局最大6個の重要局面、軽量上位5候補、選択順位、深度、nodes、scoreは`results/existing_agent_analysis/representative_matches`へ保存した。

AlphaBetaとPVSは同じ状態を交互に担当しないため、「一対局中ずっと同じ手を選んだ」という直接比較は定義できない。代わりに固定同一局面90/90一致と直接対決代表局を提示する。

## 15、辞書構造との関係

全辞書で開始可能文字は67、安全開始可能文字も67、行き止まり文字は1だった。最大強連結成分はD1000の61からD5000以上の66へ増えた。Dが増えるほど安全語・辺種類・大きい循環成分が増え、平均手数が伸びた。

D1000はdanger/near-death出現率31.5%に対し、D20000は約2.0〜2.7%だった。大辞書では安全な選択肢が長く残り、危険状態へ到達するまでが長い。

相関は7辞書という小標本で、Dと構造量が強く共変する。`dictionary_analysis/correlations.csv`は記述用であり、統計的有意差や因果を主張しない。

## 16、既存AIの長所と短所

### AlphaBeta

- 長所: PVSと同じ判断、最終D5ではPVSより速く少nodes、Beamへ12勝2敗
- 短所: 候補8外は探索しない。大候補局面で平均0.133秒

### PVS

- 長所: 固定D4では僅かに少nodes、再探索率1.25%と低い
- 短所: D5実対局ではAlphaBetaより多nodes・低速。強さは同じ

### BeamNegamax

- 長所: 一nodeが軽い、計算量上限が明確、勝つ対局は短い
- 短所: 主要AIへ2勝12敗ずつ。normal局面で参照手落ち、長期戦に弱い

### Minimax

- 長所: 単純で基準実装として有用。D5000以下では16/24勝
- 短所: 枝刈りがなく大辞書へ拡張しづらい。比較対象辞書が限定

### Greedy

- 長所: 一手約0.2msで説明しやすい
- 短所: 0/48勝。先読みなしでは有限語彙の罠を避けられない

## 17、ハイブリッドAIへの示唆

主探索はAlphaBetaが最適である。PVSは同じ手で最終設定では遅く、標準切替先にする根拠がない。Beamを通常の主探索にすると参照手落ちと長期戦敗北が増える。

最も有望なのは「AlphaBeta主系、時間逼迫時だけBeamを完走保証用バックアップにし、危険・終盤では候補制限を緩めたAlphaBetaを維持する」構成である。詳細は`hybrid_agent_design_proposal.md`に記載した。

## 18、分析上の限界

1. 108局は異なる条件の組合せで、独立同分布標本ではない。
2. D1000〜D10000はseed 0だけで、サイズとseed効果を完全分離できない。
3. AlphaBeta参照手は真の最善手ではない。
4. Beam深層のどの幅で参照経路が消えたかは現在のログだけでは未確定。
5. 反実仮想は一手置換で、敗因の証明ではない。
6. 時間制限付き探索は実行時間で完了候補数が変わり、1/108局で手数が再現しなかった。
7. 追加トレースは3回timeoutし、元計測の0回とは測定環境が異なる。
8. `own_safe_*`は選択前集計であり、将来自分へ戻る安全手そのものではない。
9. MinimaxはD5000以下だけで全体比較できない。
10. Wilson区間を出しても条件間の依存性は解消しないため、統計的有意差は主張していない。

## 19、結論

AlphaBetaとPVSは判断の強さが同じで、現在のD5ではAlphaBetaの方が単純かつ高速だった。Beamは短期決着能力と時間予測性を持つが、normalの多候補局面で参照手を外し、主要AIへの直接対決と長期戦で弱い。

Beam幅8外の一手を参照手へ変えた20局中5局で勝敗が改善し、12局で長く生存したため、候補削減が実際の結果へ関係する具体的証拠は得られた。したがって、後続HybridAgentではBeamを無条件に主探索へせず、AlphaBetaを基礎にして時間不足時だけ限定利用するのが妥当である。

## 付録、再実行とテスト

```bash
.venv/bin/python src/run_existing_agent_analysis.py --quick
.venv/bin/python src/run_existing_agent_analysis.py --full
.venv/bin/python src/run_existing_agent_analysis.py --full --stage beam-analysis
.venv/bin/python -m unittest discover -s tests
```

今回、分析用に12テストを追加した。既存テストを含む127件はすべて成功した。勝敗、先後、直接対決、D別、seed別、重複排除、PVS再探索、Beam参照手保持、risk、手数、反実仮想の状態復元、代表対局参照、CLIモードを検証している。

主な機械可読成果物:

- `results/existing_agent_analysis/summary.json`
- `results/existing_agent_analysis/summary.csv`
- `results/existing_agent_analysis/matchups`
- `results/existing_agent_analysis/search_efficiency`
- `results/existing_agent_analysis/beam_analysis`
- `results/existing_agent_analysis/risk_analysis`
- `results/existing_agent_analysis/counterfactual`
- `results/existing_agent_analysis/representative_matches`
- `results/existing_agent_analysis/dictionary_analysis`
- `results/existing_agent_analysis/plots`
