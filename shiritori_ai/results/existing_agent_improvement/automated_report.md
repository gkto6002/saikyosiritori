# 既存探索AI改善・自動集計レポート

- commit: `1b4c28318343c046a50fd9d77d4ed7af6cea83aa`
- mode: `full`

## 選択設定

- alpha_beta: `alpha_beta_d5_b8`
- beam_negamax: `beam_d5_w8-6-4-2`
- pvs: `pvs_d5_b8`

## Beam参照手保持率

- all: top2=0.889, top4=0.889, top8=0.889, top12=0.889, top16=1.000
- normal: top2=0.778, top4=0.778, top8=0.778, top12=0.778, top16=1.000
- caution: top2=1.000, top4=1.000, top8=1.000, top12=1.000, top16=1.000
- danger: top2=1.000, top4=1.000, top8=1.000, top12=1.000, top16=1.000
- critical: top2=1.000, top4=1.000, top8=1.000, top12=1.000, top16=1.000

## 最終対局

- 対局数: 108
- 内部タイムアウト: 0
- 試合時間切れ: 0

## 最終対局のAI別集計

- alpha_beta: 35/48勝 (勝率0.729)、平均思考時間0.082735秒、内部タイムアウト0
- beam_negamax: 22/48勝 (勝率0.458)、平均思考時間0.074480秒、内部タイムアウト0
- greedy: 0/48勝 (勝率0.000)、平均思考時間0.000236秒、内部タイムアウト0
- minimax: 16/24勝 (勝率0.667)、平均思考時間0.025470秒、内部タイムアウト0
- pvs: 35/48勝 (勝率0.729)、平均思考時間0.091951秒、内部タイムアウト0

## 再実行用情報

- source fingerprint: `80721518bd376abdeb31b4530ddea3f9cc04cb026e04554061fb8b44abbaf046`
- 集計CSV/JSON: `results/existing_agent_improvement/analysis`
- 図: `results/existing_agent_improvement/figures`
