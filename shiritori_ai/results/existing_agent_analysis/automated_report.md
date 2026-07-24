# 既存AI詳細分析・自動要約

- 基準対局: 108
- 追加トレース: 108局、8216手
- 元勝者一致: 108/108
- 追加トレース内部timeout: 3

## 主要AI直接対決

- alpha_beta vs beam_negamax: 12/14勝
- alpha_beta vs pvs: 7/14勝
- beam_negamax vs alpha_beta: 2/14勝
- beam_negamax vs pvs: 2/14勝
- pvs vs alpha_beta: 7/14勝
- pvs vs beam_negamax: 12/14勝

## Beam参照手保持率（実対局局面）

- top 2: 68.205%
- top 4: 80.152%
- top 6: 90.265%
- top 8: 95.070%
- top 12: 99.052%
- top 16: 100.000%
- 幅8外: 78局面
- 反実仮想で敗北から勝利: 5局面

## 注意状態

- 対象: 445局面
- 候補間でsurvival scoreが異なる: 445
- survival込みで静的1位が変化: 3

詳細は `docs/agent_analysis/existing_agent_detailed_analysis.md` を参照。
