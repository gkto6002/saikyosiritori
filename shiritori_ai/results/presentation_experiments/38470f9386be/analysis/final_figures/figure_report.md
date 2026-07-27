# 発表用グラフ再集計レポート

既存のJSONL、JSON、CSV、manifestだけから再集計した。対局や探索の再実行は行っていない。

## 01 基本6手法の総当たり勝率

- raw: `initial6/raw_matches.jsonl`
- 抽出条件: D10000、1手1秒、6手法全組合せ・先後入替
- 使用対局数: 90局
- 再計算値: Random 0.0%、Monte Carlo 20.0%、Greedy 40.0%、Minimax 63.3%、Full AlphaBeta 86.7%、Selective AlphaBeta 90.0%
- 変更点: 縦棒から発展順の横棒へ変更し、Wilson区間を併記。
- 発表用一文: 単純手法から先読み探索へ進むにつれ、同じ1秒制限下で高い勝率が得られた。
- 断定できないこと: 各手法の深度や候補上限が異なるため、探索原理だけの因果効果ではない。

## 02 候補制限による探索量と選択手の変化

- raw: `fixed_comparison/raw_runs.jsonl`
- 抽出条件: 深度5、Fullと候補上限12、固定50局面
- 比較可能局面: 40/50
- 平均時間: Full 1.307秒、Selective 0.201秒
- 平均ノード: Full 13969、Selective 2301
- 選択手一致率: 92.5%
- 評価値一致率: 82.5%
- 変更点: 時間・ノード・手一致を一枚の3パネルへ統合。
- 発表用一文: 候補制限は手の一致を概ね保ちながら、探索量を大幅に削減した。
- 断定できないこと: Fullが完了しなかった10局面の手の正しさは比較していない。

## 03 Beam探索へのAlphaBeta枝刈りの導入

- raw: `results/hybrid_agent_comparison/benchmark/821264dd868d/runs.jsonl`
- 抽出条件: 同一深度5、同一14固定局面、幅8/6/4/2
- 使用局面数: 14局面
- 平均時間: Beam 0.0917秒、Beam AlphaBeta 0.0265秒（71.1%削減）
- 平均ノード: Beam 1350、Beam AlphaBeta 404（70.1%削減）
- 変更点: 時間とノードを一枚の2パネルへ統合。
- 発表用一文: AlphaBeta枝刈りを加えることで、同一深度のBeam探索量を約7割削減した。
- 断定できないこと: この図は探索量比較であり、勝率向上を直接示さない。

## 04 主要4手法の総当たり勝率

- raw: `final4/raw_matches.jsonl`
- 抽出条件: D10000、1手1秒、4手法全組合せ・先後入替
- 使用対局数: 120局
- 再計算値: Selective AlphaBeta 58.3%、PVS 50.0%、Beam AlphaBeta 40.0%、Beam PVS 51.7%
- 変更点: 共通条件120局だけを使用し、直接対戦の追加20局を加えていない。
- 発表用一文: 主要4手法の総当たりでは、Beam AlphaBetaの明確な優位性は確認できなかった。
- 断定できないこと: 4方式間の勝率差はWilson区間が重なり、統計的有意差を示すものではない。

## 05 Beam AlphaBetaとSelective AlphaBetaの直接対戦

- raw: `beam_hybrid_followup/.../raw_matches.jsonl` と `final4/raw_matches.jsonl`
- 抽出条件: 両手法の深度・幅・候補上限・適応設定・1秒制限が一致する直接対戦のみ
- 使用対局数: 40局
- Beam AlphaBeta: 23勝17敗、57.5%
- Selective AlphaBeta: 17勝23敗、42.5%
- 変更点: 20局ずつを別表示せず、同一設定の全40局へ統合。
- 発表用一文: Beam AlphaBetaはSelective AlphaBetaとの全40局で23勝17敗だった。
- 断定できないこと: この40局には設定選定に利用した対局を含むため、データ分離を前提とする評価ではない。

## 06 平均実効深度と総当たり勝率

- raw: `final4/raw_matches.jsonl`
- 抽出条件: 主要4手法の共通条件120局
- 使用対局数: 120局
- 再計算値: Selective AlphaBeta 深度6.11・勝率58.3%、PVS 深度6.01・勝率50.0%、Beam AlphaBeta 深度8.89・勝率40.0%、Beam PVS 深度8.84・勝率51.7%
- 変更点: 時間と深度の棒図から、深度と勝率の散布図へ変更。
- 発表用一文: Beam系は深く探索できたが、探索深度だけでは勝率は決まらなかった。
- 断定できないこと: 4点のみのため相関や回帰関係は評価していない。

## 補足 Beam AlphaBetaの深度と幅の比較

- raw: `results/beam_hybrid_followup/D10000/c86fc7661da6/raw_matches.jsonl`
- 抽出条件: 各設定をSelective AlphaBetaと20局、設定間の合算なし
- 再計算値: baseline 10勝10敗・50.0%（n=20）、deep 4勝16敗・20.0%（n=20）、wide 8勝12敗・40.0%（n=20）、deep_wide 16勝4敗・80.0%（n=20）
- 変更点: 各設定を分離したまま一枚へまとめ、勝敗数と対局数を併記。
- 発表用一文: 深度とルート付近の幅を同時に増やした設定が、この比較では最も高い勝率だった。
- 断定できないこと: 設定候補を選んだ対局なので、方式全体の一般的優位性ではない。

## 07 盤面適応型と固定型の勝率比較

- raw: `results/minimal_adaptive_hybrid/D10000/round_robin_matches.jsonl`
- 抽出条件: D10000、5設定の総当たり100局、1手0.3秒、適応深度8→9、Beam幅12/8/4/2
- 辞書seed: [0, 1, 2, 3, 4]、各seedで全組合せを先後入替
- 先後条件: 各設定40局、先手20局・後手20局
- 再計算値: fixed_beam_alpha_beta 20勝20敗・50.0%（n=40）、gap_conservative 19勝21敗・47.5%（n=40）、gap_responsive 10勝30敗・25.0%（n=40）、proof_strict 23勝17敗・57.5%（n=40）、proof_moderate 28勝12敗・70.0%（n=40）
- Proof系の扱い: proof_strictとproof_moderateは閾値と完全解析上限が異なるため統合せず、別の棒として表示。
- 固定型との直接対戦: gap_conservative 3勝7敗、gap_responsive 3勝7敗、proof_strict 7勝3敗、proof_moderate 7勝3敗
- 変更点: 固定型を基準色・斜線・枠線で強調し、盤面適応型4設定を同系色で比較。
- 発表用一文: 固定型を明確に上回る盤面適応型は確認できなかった。
- 断定できないこと: Proof Moderateは総当たり70.0%だが、各方式40局でWilson区間が重なるため、統計的な優位性や一般的な強さは断定できない。

## 発表全体の結論

候補制限と枝刈りによって探索量を削減し、より深い探索が可能になった。Beam AlphaBetaはSelective AlphaBetaとの全40局で23勝17敗だったが、主要4手法の総当たりでは明確な優位性は確認できなかった。このことから、探索の深さだけでなく、Beamに残す候補の選び方も重要だと考えられる。

## 自動検査

```json
{
  "direct_match_count": 40,
  "direct_beam_alpha_beta_wins": 23,
  "direct_selective_alpha_beta_wins": 17,
  "direct_draw_count": 0,
  "direct_duplicate_match_id_count": 0,
  "direct_beam_first_count": 20,
  "direct_selective_first_count": 20,
  "direct_settings_match": true,
  "recorded_evaluation_and_game_settings_match": true,
  "four_agent_match_count": 120,
  "four_agent_unique_match_count": 120,
  "initial_match_count": 90,
  "initial_unique_match_count": 90,
  "fixed_position_count": 50,
  "fixed_comparable_position_count": 40,
  "representative_depth": 5,
  "required_values": {
    "direct_match_count": 40,
    "direct_beam_alpha_beta_wins": 23,
    "direct_selective_alpha_beta_wins": 17,
    "direct_draw_count": 0,
    "direct_duplicate_match_id_count": 0,
    "direct_beam_first_count": 20,
    "direct_selective_first_count": 20,
    "direct_settings_match": true,
    "recorded_evaluation_and_game_settings_match": true,
    "four_agent_match_count": 120,
    "four_agent_unique_match_count": 120,
    "initial_match_count": 90,
    "initial_unique_match_count": 90,
    "fixed_position_count": 50,
    "fixed_comparable_position_count": 40,
    "representative_depth": 5
  },
  "all_data_checks_passed": true,
  "board_adaptive": {
    "match_count": 100,
    "unique_match_count": 100,
    "dictionary_size": 10000,
    "decision_time_sec": 0.3,
    "max_moves": 1000,
    "max_match_time_sec": 90.0,
    "initial_depth": 8,
    "max_depth": 9,
    "beam_widths": [
      12,
      8,
      4,
      2
    ],
    "adaptive_depth": true,
    "dictionary_seeds": [
      0,
      1,
      2,
      3,
      4
    ],
    "pair_counts": {
      "fixed_beam_alpha_beta|gap_conservative": 10,
      "fixed_beam_alpha_beta|gap_responsive": 10,
      "fixed_beam_alpha_beta|proof_strict": 10,
      "fixed_beam_alpha_beta|proof_moderate": 10,
      "gap_conservative|gap_responsive": 10,
      "gap_conservative|proof_strict": 10,
      "gap_conservative|proof_moderate": 10,
      "gap_responsive|proof_strict": 10,
      "gap_responsive|proof_moderate": 10,
      "proof_moderate|proof_strict": 10
    },
    "all_profiles_have_40_games": true,
    "all_profiles_have_balanced_seats": true,
    "draw_count": 0,
    "match_timeout_count": 0,
    "invalid_move_count": 0,
    "profiles_kept_separate": [
      "fixed_beam_alpha_beta",
      "gap_conservative",
      "gap_responsive",
      "proof_strict",
      "proof_moderate"
    ],
    "vs_fixed": {
      "gap_conservative": {
        "games": 10,
        "wins": 3,
        "losses": 7,
        "win_rate": 0.3
      },
      "gap_responsive": {
        "games": 10,
        "wins": 3,
        "losses": 7,
        "win_rate": 0.3
      },
      "proof_strict": {
        "games": 10,
        "wins": 7,
        "losses": 3,
        "win_rate": 0.7
      },
      "proof_moderate": {
        "games": 10,
        "wins": 7,
        "losses": 3,
        "win_rate": 0.7
      }
    }
  },
  "images": {
    "image_count": 8,
    "all_openable": true,
    "all_16_9": true,
    "all_high_resolution": true,
    "details": [
      {
        "file": "01_initial_agents_win_rate.png",
        "width": 2816,
        "height": 1584,
        "aspect_ratio": 1.7777777777777777,
        "valid_16_9": true,
        "minimum_slide_resolution": true
      },
      {
        "file": "02_selective_alpha_beta_effect.png",
        "width": 2816,
        "height": 1584,
        "aspect_ratio": 1.7777777777777777,
        "valid_16_9": true,
        "minimum_slide_resolution": true
      },
      {
        "file": "03_beam_pruning_effect.png",
        "width": 2816,
        "height": 1584,
        "aspect_ratio": 1.7777777777777777,
        "valid_16_9": true,
        "minimum_slide_resolution": true
      },
      {
        "file": "04_four_agents_round_robin.png",
        "width": 2816,
        "height": 1584,
        "aspect_ratio": 1.7777777777777777,
        "valid_16_9": true,
        "minimum_slide_resolution": true
      },
      {
        "file": "05_beam_alpha_beta_direct.png",
        "width": 2816,
        "height": 1584,
        "aspect_ratio": 1.7777777777777777,
        "valid_16_9": true,
        "minimum_slide_resolution": true
      },
      {
        "file": "06_search_depth_and_strength.png",
        "width": 2816,
        "height": 1584,
        "aspect_ratio": 1.7777777777777777,
        "valid_16_9": true,
        "minimum_slide_resolution": true
      },
      {
        "file": "07_board_adaptive_comparison.png",
        "width": 2816,
        "height": 1584,
        "aspect_ratio": 1.7777777777777777,
        "valid_16_9": true,
        "minimum_slide_resolution": true
      },
      {
        "file": "appendix_beam_parameters.png",
        "width": 2816,
        "height": 1584,
        "aspect_ratio": 1.7777777777777777,
        "valid_16_9": true,
        "minimum_slide_resolution": true
      }
    ]
  }
}
```
