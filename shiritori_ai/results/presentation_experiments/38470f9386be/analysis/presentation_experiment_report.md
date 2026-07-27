# 発表用追加実験レポート

## 条件とデータ分離

- Git commit: `a4e41f35c3009743e2bbf005729ce5179fda865a`
- source fingerprint: `13f2ffed886daaeea903a5e69669fe549c9afd8a0f72e1689a8a0a013822854b`
- 設定選定seed: 0〜9（探索的結果）
- 未使用確認seed: 10, 11, 12, 13, 14, 15, 16, 17, 18, 19
- D10000、2〜12文字、1手1秒、直列実行
- 未使用seedの結果をseed 0〜9の勝率へ合算していない。

## 使用設定

| 手法 | 初期深度 | 最大深度 | 候補上限 / Beam幅 | 適応深度 |
|---|---:|---:|---|---|
| Random | - | - | - | - |
| Monte Carlo | - | - | 候補20・playout 10 | - |
| Greedy | 1 | 1 | - | なし |
| Minimax | 3 | 3 | 8 | なし |
| Full AlphaBeta | 4 | 4 | 全候補 | なし |
| Selective AlphaBeta | 5 | 7 | 8 | あり |
| PVS | 5 | 7 | 8 | あり |
| Beam AlphaBeta | 8 | 9 | 12, 8, 4, 2 | あり |
| Beam PVS | 8 | 9 | 12, 8, 4, 2 | あり |

適応深度4手法は目標0.6秒、低下閾値0.95、回復閾値0.6、回復待ち2手で統一した。

## 自動検査

```json
{
  "final4": {
    "expected_count": 120,
    "actual_count": 120,
    "unique_count": 120,
    "duplicate_count": 0,
    "invalid_move_count": 0,
    "match_timeout_count": 0,
    "max_moves_count": 0,
    "internal_timeout_count": 178,
    "missing_scalar_value_count": 0,
    "missing_seat_pairs": [],
    "complete": true
  },
  "initial6": {
    "expected_count": 90,
    "actual_count": 90,
    "unique_count": 90,
    "duplicate_count": 0,
    "invalid_move_count": 0,
    "match_timeout_count": 0,
    "max_moves_count": 0,
    "internal_timeout_count": 52,
    "missing_scalar_value_count": 0,
    "missing_seat_pairs": [],
    "complete": true
  },
  "fixed_comparison": {
    "expected_count": 300,
    "actual_count": 300,
    "unique_count": 300,
    "duplicate_count": 0,
    "complete": true
  }
}
```

## 固定局面 Full対Selective

代表深度は、Fullのルート完了率80%以上という事前規則により深度5とした。選択手一致率では選定していない。

| 深度 | Full完了 | 比較可能 | 手一致 | 評価一致 | Full秒 | Selective秒 | Full nodes | Selective nodes |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 100.0% | 50/50 | 86.0% | 74.0% | 0.7239 | 0.0170 | 7685.0 | 185.5 |
| 4 | 92.0% | 46/50 | 84.8% | 80.4% | 1.0042 | 0.0550 | 13746.6 | 646.4 |
| 5 | 80.0% | 40/50 | 92.5% | 82.5% | 1.3069 | 0.2010 | 13969.0 | 2300.6 |

## 未使用seedの最終4手法

| 手法 | 対局 | 勝-敗-分 | 勝率 | 平均秒 | 平均深度 | 内部timeout |
|---|---:|---:|---:|---:|---:|---:|
| Selective AlphaBeta | 60 | 35-25-0 | 58.3% | 0.3138 | 6.11 | 74 |
| PVS | 60 | 30-30-0 | 50.0% | 0.3185 | 6.01 | 86 |
| Beam AlphaBeta | 60 | 24-36-0 | 40.0% | 0.1830 | 8.89 | 6 |
| Beam PVS | 60 | 31-29-0 | 51.7% | 0.1967 | 8.84 | 12 |

Beam AlphaBetaの総当たり勝率は40.0%（24勝36敗0分、n=60）だった。

### Beam AlphaBeta直接対戦

- vs Selective AlphaBeta: 7勝13敗0分、35.0%（n=20）
- vs PVS: 7勝13敗0分、35.0%（n=20）
- vs Beam PVS: 10勝10敗0分、50.0%（n=20）

## 確認実験からの結論

- Beam AlphaBetaは平均思考時間0.183秒、平均実効深度8.89で、Selective AlphaBetaより高速かつ深く探索した。
- ただし未使用seedの勝率は40.0%で、調整seedで観測した勝率優位は再現しなかった。
- Beam AlphaBetaの直接成績はSelective AlphaBetaに7勝13敗、PVSに7勝13敗、Beam PVSに10勝10敗だった。
- したがって発表では「探索効率の改善」は主張できるが、「未使用辞書でも最強」は主張できない。


## 初期6AI

| 手法 | 対局 | 勝-敗-分 | 勝率 |
|---|---:|---:|---:|
| Random | 30 | 0-30-0 | 0.0% |
| Monte Carlo | 30 | 6-24-0 | 20.0% |
| Greedy | 30 | 12-18-0 | 40.0% |
| Minimax | 30 | 19-11-0 | 63.3% |
| Full AlphaBeta | 30 | 26-4-0 | 86.7% |
| Selective AlphaBeta | 30 | 27-3-0 | 90.0% |

## 既存結果の再利用

- 同一深度5のAlphaBeta、Beam、Beam AlphaBeta比較は`results/hybrid_agent_comparison/benchmark/821264dd868d/summary.json`から読み取った。
- Beamの深度・幅追試は`results/beam_hybrid_followup/D10000/c86fc7661da6/analysis/variant_summary.json`から読み取った。
- 盤面適応型の修正前180局は使用していない。

## 完全解析ハイブリッドの扱い

- 完全解析正解データ作成: 0/30局面完了。
- proof方式の非自明成功合計: 0。
- proof方式による選択変更合計: 0。
- 非自明局面での改善は確認されていないため、強さが向上したとは表現しない。

## グラフ別の読み方

### 図01

- 使用データ: 初期6AI・未使用seed 3個・90局
- 直接言えること: 同一1秒制限下の実用設定の勝率
- 言えないこと: 探索原理だけの因果効果や同一深度の強さ
- スライド用一文: 同じ時間制限の実用設定では、探索手法ごとに成績差が見られた。

### 図02

- 使用データ: 固定50局面・代表深度5
- 直接言えること: FullとSelectiveの平均時間差
- 言えないこと: タイムアウト局面を除いた純粋計算量だけの差
- スライド用一文: 候補制限による平均思考時間の変化を示す。

### 図03

- 使用データ: 固定50局面・代表深度5
- 直接言えること: 平均探索ノード数
- 言えないこと: ノード1個あたりの計算コスト
- スライド用一文: Selectiveは探索対象を絞ることでノード数を削減した。

### 図04

- 使用データ: 固定50局面・比較可能40局面
- 直接言えること: 完了局面上の手・評価一致
- 言えないこと: 未完了局面における正解率
- スライド用一文: 品質比較の分母を両方式が完了した局面に限定した。

### 図05-06

- 使用データ: 既存同一深度5・14局面
- 直接言えること: BeamへのAlphaBeta導入前後の時間とノード
- 言えないこと: 対局勝率の改善
- スライド用一文: 枝刈り併用により同一深度の探索量が変化した。

### 図07

- 使用データ: 既存seed 0〜9・各設定20局
- 直接言えること: 調整段階の対AlphaBeta勝率
- 言えないこと: 未使用seedへの一般化
- スライド用一文: 深度とルート幅へ計算量を再配分した設定を比較した。

### 図08-10

- 使用データ: 未使用seed 10〜19・120局
- 直接言えること: 最終4手法の確認実験
- 言えないこと: seed 0〜9と合算した母集団勝率
- スライド用一文: 未使用辞書seedで最終設定の再現性を確認した。

## 生成グラフ

- `01_initial_agents_win_rate.png`
- `02_full_selective_time.png`
- `03_full_selective_nodes.png`
- `04_full_selective_quality.png`
- `05_beam_pruning_time.png`
- `06_beam_pruning_nodes.png`
- `07_beam_depth_width_win_rate.png`
- `08_unseen_seed_round_robin.png`
- `09_unseen_seed_beam_direct.png`
- `10_unseen_seed_efficiency.png`
