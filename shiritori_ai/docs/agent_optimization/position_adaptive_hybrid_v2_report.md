# 盤面適応型ハイブリッド修正版（v2）

## 目的と基準

この実装はコミット`c4ad512`を基準に、修正前D10000・180局で判明した
実装不備を直し、終端局面証明拡張型を追加したものである。修正前rawデータは
`results/position_adaptive_hybrid/`へ残し、修正後は
`results/position_adaptive_hybrid_v2/`へ保存する。両者を混ぜて集計しない。

既存の固定BeamAlphaBeta、固定BeamPVS、評価関数、標準深度と標準Beam幅は
変更していない。

## 変更ファイル

- `src/agents.py`: 共通候補確定hookと探索末端評価hook。
- `src/search_common.py`: ply別Beam除外数。
- `src/adaptive_hybrid.py`: 動的Beam・反復深化修正、証明拡張2方式。
- `src/match.py`: Beam/完全解析の対局ログ。
- `src/run_graph_control_comparison.py`: 新エージェント名と設定登録。
- `src/run_position_adaptive_hybrid_experiment.py`: v2の4段階実験。
- `src/analyze_position_adaptive_hybrid_experiment.py`: ply別・完全解析・
  seedクラスタ集計。
- `tests/test_adaptive_hybrid.py`、`tests/test_position_adaptive_hybrid_experiment.py`:
  修正と実験設計の回帰テスト。
- `README.md`と本書、旧計画書・旧結果書: 実行方法と旧結論の訂正。

## 再検証した指摘

次の指摘はコードと旧ログの両方から正しいと確認した。

- DynamicBeamAlphaBeta / DynamicBeamPVSはrootの候補にだけ
  `_select_root_candidates`を適用し、再帰探索の`_ordered_edges`では
  動的幅による切り詰めを行っていなかった。
- そのため動的幅ログはply 0に偏り、固定BeamよりBeam除外数が極端に少なかった。
- ResearchAdaptiveBeam / IntegratedAdaptiveHybridも同じmixinを継承していた。
- ResearchAdaptiveBeamは開始深度7に対し外側の実効深度が3〜6へ下がり、
  一手内で複数深度を完了できず、旧180局ではモード切替が0回だった。
- 時間成長率用の更新順が一段遅く、現在深度と直前完了深度ではなく、
  一つ古い時間を参照する場合があった。
- EndgameExactHybridの旧成功14件は、すべて一辺種類・一状態の自明な解析だった。
- BranchSwitchAlphaBetaはroot低分岐でも到達可能部分が大きく、
  全幅探索へ切り替えた判断の54.5%が時間切れだった。

したがってBranchSwitchの仮説は今回の条件では否定、EndgameExactHybridは
安全性のみ確認済み、動的Beam系4方式の旧勝率は無効とする。
盤面適応型全体を不採用とする旧結論は撤回した。

## 動的Beamの修正

`SearchAgentBase._ordered_edges`へ、順序付け後の候補を確定する共通hookを追加した。
全幅・固定幅・動的幅は次のように区別される。

1. 全幅または通常branch limitは基底実装が候補を確定する。
2. 固定Beamは既存のply別`beam_widths`を順序付け上限として使う。
3. 動的Beamは全候補を既存評価で並べた後、
   候補数とplyから幅を決め、共通hook内で切り詰める。

AlphaBetaとPVSは全再帰ノードで同じ`_ordered_edges`を通るため、
rootだけでなくply 1以降にも動的幅が適用される。ログには
`beam_candidate_counts_by_ply`、`beam_selected_counts_by_ply`、
`beam_pruned_counts_by_ply`、`beam_ordering_calls_by_ply`、
`dynamic_beam_width_counts`を保存する。

候補数が`no_prune_threshold`以下の場合は「そのノードで決定した幅 =
候補総数」とし、全候補を探索する。`None`は動的幅を意味せず、
順序付け段階で固定上限を置かないことだけを意味する。

## 反復深化と時間管理

ResearchAdaptiveBeamは一手の中では自身の内部反復深化だけを実行する。
外側の適応深度は手と手の間で次手の目標深度を調整するだけであり、
一手内の反復を重ねて実行しない。この責任分担を
`depth_control=single_internal_iterative_deepening`として記録する。

開始深度は`min(configured_start, target_depth - 1)`とし、目標深度が2以上なら
最低二深度を試せるようにした。各深度について開始・終了offset、完了状態、
方式、実効深度、ノード数、null-window数、再探索数・率を保存する。

次深度予測は「現在完了深度の時間 / 直前完了深度の時間」で求める。
未完了深度は予測基準に使わない。探索前に合法fallbackを確保し、
次深度が時間切れなら最後に完了した深度の手を返す。

## ProofExtensionBeamAlphaBeta

本命候補として`proof_extension_beam_alpha_beta`を追加した。
通常探索は既存の固定BeamAlphaBetaそのもので、次の場合だけ既存
`ShiritoriSolver`へ処理を渡す。

- rootの到達可能部分が十分小さい場合。
- 深度制限へ到達したノードで、到達可能語数、辺種類数、文字頂点数、
  推定状態数、現在分岐数、残り時間の全条件を満たす場合。

完全解析は一手時間とは別に、総時間比率、秒上限、状態数上限を持つ。
通常探索へ戻る時間を`exact_normal_time_reserve_sec`で予約する。
完全解析が完了したときだけ`WIN_SCORE` / `LOSS_SCORE`系列の厳密値を採用し、
中断時は先に計算済みの通常評価へ戻る。同一ターン内の同一残存状態は
`(required_char_id, edge_counts)`でメモ化する。

原因分離のため、次を別々に指定できる。

- `beam_alpha_beta`: 完全解析なし。
- `endgame_exact_hybrid`: root限定。
- `proof_extension_beam_alpha_beta`: root + 探索末端、固定Beam。
- `dynamic_beam_alpha_beta`: 修正版動的Beamのみ。
- `dynamic_proof_extension_beam_alpha_beta`: 動的Beam + 証明拡張。

完全解析ログは呼出し位置、ply、通常残り深度、規模特徴、状態数、時間、
完了・中断、勝敗、通常評価との差、複数合法手か、自明か、メモhit、
fallbackを`exact_call_events`へ保存する。rootの手変更は通常探索を二重実行して
対局時間を増やさないため対局中は`null`とし、固定局面診断で
BeamAlphaBetaと対応付けて算出する。

## テストと小規模スモーク

全テスト:

```text
python -m unittest discover -s tests -p 'test_*.py'
Ran 212 tests in 9.811s
OK
```

追加テストでは、AlphaBeta/PVS両方の全候補選択呼出しを捕捉し、
ply 1以上で`selected_count <= decided_width`、幅以下なら全候補採用を確認した。
さらに直前完了深度からの時間予測、複数深度完了とモード切替、
時間切れfallback、非自明frontier解析、中断fallback、完全解析で
root手が「厳密には負け」から「厳密には勝ち」へ変わる既知小局面、
再現性、合法性を確認した。

D1000・4局・一手0.02秒のスモーク結果:

| agent | 判断数 | 記録ply | Beam除外数 | ノード数 | 内部timeout |
|---|---:|---|---:|---:|---:|
| BeamAlphaBeta | 45 | 0〜8 | 34,646 | 9,346 | 0 |
| DynamicBeamAlphaBeta | 32 | 0〜7 | 26,814 | 7,534 | 5 |
| DynamicBeamPVS | 12 | 0〜7 | 13,640 | 3,864 | 5 |

短すぎる0.02秒設定なので勝率評価には使わない。目的である再帰plyログ、
実質全幅探索でないこと、除外数が固定Beamと同程度の桁であることを確認した。
4局とも例外・不正手なく完了した。単体テストの既知小局面では
探索末端の非自明完全解析が起動し、6状態以上・複数合法辺の成功と、
中断後の合法fallbackを確認した。

同じ既知小局面の直接スモークでは、root完全解析0回、frontier呼出し5回、
非自明成功5回で厳密勝ち手`きえ`を選択した。`max_states=1`へ制限した別実行は
5回すべて中断・通常評価へfallbackし、内部timeoutなしで合法手を返した。
D100のResearchAdaptiveBeam直接スモークでは深度3と4を両方完了し、
予測時間条件を厳しくした設定で深度3のBeamPVSから深度4の
BeamAlphaBetaへ1回切り替わった。

## D10000実験設計

ランナーは開始前に件数と45秒/局を上限とした概算時間を表示する。
同じコマンドを再実行すると同じrun hashを使い、
`match_id`が既存の局を読み飛ばして再開する。コードまたは設定を変えた場合は
別runになる。失敗局は`failures.jsonl`へ記録し、他局を続行する。
D10000以上は`--confirm-d10000`なしでは開始しない。

| 段階 | seed | 内容 | 件数 | 保守的概算 |
|---|---|---|---:|---:|
| verify | 0 | 固定Beam vs Dynamic AB/PVS、先後交換 | 4局 | 約3分 |
| tune | 0〜4 | 6調整方式 × 2 profile + 2基準方式、先後 | 140局 | 約1時間45分 |
| final | 10〜39 | 主要3方式 vs 固定Beam、先後 | 180局 | 約2時間15分 |
| fixed | 保存14局面 | 全11方式、固定深度8 | 154判断 | 約3分+集計 |

旧180局のseed 0〜4は調整専用とし、finalのseed 10〜39とは分離する。
finalは主要対戦ごとに30 seed × 先後 = 60局である。seed 10〜59へ拡張すれば
主要対戦ごとに100局へ増やせる。集計は通常のWilson区間に加え、
先後を同じ辞書seedのクラスタとして再標本化する決定的bootstrap区間を
`direct_matchups.csv`へ出力する。

## 段階順の実行コマンド

### 0. final用辞書seed 10〜39を生成

```bash
.venv/bin/python src/experiment_dictionary.py \
  --master data/master/master_dictionary.jsonl \
  --size 10000 \
  --seeds 10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39 \
  --min-length 2 \
  --max-length 12 \
  --output data/dictionaries
```

### 1. 修正確認

```bash
.venv/bin/python -u src/run_position_adaptive_hybrid_experiment.py \
  --stage verify \
  --dictionary-size 10000 \
  --confirm-d10000 \
  --analyze
```

### 2. 調整

```bash
.venv/bin/python -u src/run_position_adaptive_hybrid_experiment.py \
  --stage tune \
  --dictionary-size 10000 \
  --confirm-d10000 \
  --analyze
```

出力末尾のrunディレクトリを`<tune-run>`とする。選定ファイルは
`<tune-run>/analysis/selected_profile.json`である。
シェルで最新の選定ファイルを変数へ入れる場合は次を実行する。

```bash
TUNE_SELECTION=$(find results/position_adaptive_hybrid_v2/tune/D10000 \
  -path '*/analysis/selected_profile.json' -type f -print0 \
  | xargs -0 ls -t | head -n 1)
echo "$TUNE_SELECTION"
```

### 3. 未使用seedで最終評価

```bash
.venv/bin/python -u src/run_position_adaptive_hybrid_experiment.py \
  --stage final \
  --dictionary-size 10000 \
  --selection-from "$TUNE_SELECTION" \
  --confirm-d10000 \
  --analyze
```

### 4. 保存局面・固定深度診断

```bash
.venv/bin/python -u src/run_position_adaptive_hybrid_experiment.py \
  --stage fixed \
  --dictionary-size 10000 \
  --selection-from "$TUNE_SELECTION" \
  --confirm-d10000 \
  --analyze
```

中断時は、途中で使ったものと完全に同じコマンドをもう一度実行する。
集計だけ再実行する場合:

```bash
.venv/bin/python src/analyze_position_adaptive_hybrid_experiment.py \
  --input <run-directory>
```

## 本実験後に確認する仮説

- 修正DynamicBeamのply別除外数が固定Beamと同程度で、実効深度を維持できるか。
- DynamicBeamAlphaBetaが固定BeamAlphaBetaより同時間で勝率を改善するか。
- frontier完全解析のうち非自明成功が何件あり、通常評価と手を何件変えるか。
- 証明拡張の手変更が厳密勝敗および対局勝率を改善するか。
- 完全解析時間が通常探索時間・実効深度・timeout率を悪化させないか。
- 動的Beam + 証明拡張の効果が各単体の効果を上回るか。
- ResearchAdaptiveBeamが複数深度を完了し、再探索率が次深度時間切れを
  実際に予測するか。発火しない場合は再評価対象から外す。
