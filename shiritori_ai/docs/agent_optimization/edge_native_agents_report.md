# 辺ネイティブAI移行レポート

## 目的

Random、Greedy、Minimax、AlphaBeta、MonteCarloをword ID探索から有向多重グラフの辺探索へ移し、AI対AIでは具体語を一切状態・探索・履歴へ持ち込まない。人間対AIでは、入力と表示に必要な場合だけ具体語を管理する。

## 確認した既存コード

- `src/agents.py`: 五つの近似AI、共通評価式、適応depth、branch limit
- `src/runtime_dictionary.py`: word配列、辺数、CSR単語バケット
- `src/runtime_state.py`: AI辺状態、人間用具体語状態、旧word IDアダプタ
- `src/match.py`: 旧単語対局とRuntime対局
- `src/experiments_approx.py`: AI組合せ実験とログ・集計
- `src/human_cli.py`: 旧WordGraphによる人間入力・AI表示

## 変更したファイル

- `src/runtime_dictionary.py`
- `src/runtime_state.py`
- `src/agents.py`
- `src/match.py`
- `src/experiments_approx.py`
- `src/human_cli.py`
- `src/dictionary_stats.py`
- `tests/test_runtime_state.py`
- `tests/test_agents_match.py`
- `README.md`

## 追加したファイル

- `tests/test_edge_agents.py`
- 本レポート

## 採用した設計

### AI対AI

`RuntimeDictionary`から単語フィールドを除いた`EdgeDictionary`を作る。AIへ渡す`AIEdgeState`は次だけを保持する。

- `EdgeDictionary`: 文字ID、初期辺数、初期active mask
- `required_char_id`
- `edge_counts`
- `active_end_masks`
- `edge_history`

`EdgeDictionary`には`word_readings`、`word_to_id`、word ID配列、単語バケットが存在しない。旧`RuntimeAgentAdapter`と辺履歴の単語materializationは削除した。

### 人間対AI

`HumanRuntimeState`だけが`RuntimeDictionary`、`used_word_ids`、`bucket_cursors`、`word_history`を持つ。AI思考時は現在の辺数を`AIEdgeState`へコピーし、確定したstart/end IDを`choose_ai_word`へ渡す。具体語は確定後に未使用バケットから一語だけ選ぶ。

## AIごとの対応

- Random: 安全な辺を優先し、辺数を重みとして抽選する。旧方式の単語一様抽選と辺選択確率を合わせる。
- Greedy: 相手の合法語数、安全語数、`ん`終端語数を辺数の行合計から計算する。旧評価式の係数は変更しない。
- Minimax: 同一状態を`apply_edge`／`undo_edge`しながらnegamaxする。depthと適応depthは従来値を維持する。
- AlphaBeta: 辺negamaxへ従来のalpha-beta条件をそのまま適用し、pruned countを維持する。
- MonteCarlo: 多重度重み付きで辺を選び、playout終了後に全辺をundoする。playout方針とmobility打切り評価を維持する。

同じstart/endの語は同じゲーム遷移なので、候補列挙とbranch limitの単位を具体語から異なる辺種類へ変更した。同一辺は`edge_counts`の残数まで繰り返し使用できる。

## AI対AI対局

`simulate_runtime_match`は`EdgeDictionary`だけで実行できる。履歴にはstart/end ID、文字、edge index、使用前後の辺数、思考統計だけを保存し、`word`と`word_id`を保存しない。

`experiments_approx.py --runtime <runtime.json>`を標準経路にした。辞書条件は隣接metadataから取得し、文字数条件を再指定しない。旧`--runtime-dir`、`--records`、`--jmdict`も残すが、対局は同じ辺専用関数で行う。文字分布集計も辺数から直接計算する。

## 互換性と差分

- 旧`choose_move`、`GameState`、`WordGraph`、`simulate_match`は比較用に残した。
- Greedy評価値と局面評価値は、多重辺を含むfixtureで旧word方式と一致した。
- Randomの辺選択確率は辺数重みで旧単語抽選と一致する。
- 同点手の順序は旧方式の単語辞書順から、安定した`start_id/end_id`順へ変わる。
- branch limitは単語数ではなく異なる辺種類数に適用される。これは辺ネイティブ化による意図的な差分である。
- AI対AIログの旧`used_word_count`列はCSV互換のため残し、値は使用した辺インスタンス数を表す。

## テスト

```bash
python -m unittest discover -s tests -v
python -m py_compile src/*.py benchmarks/*.py
```

検証内容:

- AI状態とEdgeDictionaryに単語フィールドが存在しない
- 五手法が合法辺を返す
- 全探索後に辺数、mask、履歴が完全に戻る
- Greedy・局面評価が旧word方式と一致する
- AI対AI履歴にword／word IDが存在しない
- 人間状態だけが具体語を保持し、AI確定辺を未使用語へ変換する
- 辺分布集計が旧WordGraph集計と一致する

## 実データ確認

D100の全20通りの異なるAI組合せを辺専用経路で完走した。28手のログすべてにedge indexがあり、word／word IDは0件だった。

D10000の初期局面、0.05秒制限、Minimax・AlphaBeta深さ2の参考値:

- Random: 0.000812秒
- Greedy: 0.002866秒
- Minimax: 0.010430秒
- AlphaBeta: 0.004974秒
- MonteCarlo: 0.009815秒

全手法で合法辺を返し、思考後の状態が初期状態と一致した。時間値は環境依存であり、テスト合否には使わない。

人間状態では`すわひりご`を受理後、Greedyが`ご→ん`を選び、未使用具体語`ごうまん`を割り当てて表示できることを確認した。

## 残っている問題

- 辺種類単位のbranch limitにより、旧単語辞書順の同点選択とは結果が変わり得る。
- `RuntimeDictionary`のJSON自体は人間用単語情報も持つが、AI対AIへ渡す時点で`EdgeDictionary`へ分離している。
- 完全解析も後続作業で混合基数の辺使用回数コードへ移行した。詳細は`edge_exact_solver_report.md`を参照する。
- 反復深化、置換表、手の並べ替え強化、HybridAgentは未実装である。
