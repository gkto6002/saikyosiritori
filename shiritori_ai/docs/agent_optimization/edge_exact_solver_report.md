# 辺ネイティブ完全解析レポート

## 目的

完全解析からword ID、単語文字列、使用済み単語ビットマスクを除き、有向多重グラフの辺数だけで勝敗を厳密に解析する。

## 確認した既存コード

- `src/exact_solver.py`: `(current_char, used_mask)`のメモ化再帰
- `src/experiments_exact.py`: JMdict／CSVからの辞書生成、初手単語別結果、サイズ自動増加
- `src/runtime_dictionary.py`: `EdgeDictionary`、文字ID、辺数
- `tests/test_solver.py`: 終端`ん`、勝敗、初手、タイムアウト停止条件

## 変更したファイル

- `src/exact_solver.py`
- `src/experiments_exact.py`
- `src/runtime_dictionary.py`
- `tests/test_solver.py`
- `tests/test_runtime_dictionary.py`
- `README.md`
- `docs/dictionary_optimization/final_report.md`
- `docs/agent_optimization/edge_native_agents_report.md`

## 状態表現

非空辺だけにcompact edge IDを割り当てる。辺`i`の初期多重度を`capacity[i]`とし、使用回数を`0..capacity[i]`の数字として混合基数整数へ符号化する。

```text
multiplier[0] = 1
multiplier[i+1] = multiplier[i] * (capacity[i] + 1)
edge_usage_code = Σ used_count[i] * multiplier[i]
```

一辺を使う遷移は`edge_usage_code + multiplier[i]`である。メモ化キーは次だけで、word IDを含まない。

```text
(required_char_id, edge_usage_code)
```

Pythonの任意精度整数を使うため、状態コードの桁あふれはない。辺数配列全体のtupleをメモ化キーへ入れずに済む。

## 勝敗規則

- 必要文字から始まる残存辺を列挙する。
- `ん`へ向かう辺は選んだ側の負けなので勝ち手候補にしない。
- 安全な辺を一つ使い、相手状態が負けなら現在状態を勝ちとする。
- 同じstart/end辺は初期多重度まで繰り返し使用できる。
- 安全な辺がない状態は負けとする。

## 初手結果

初手解析は具体語ごとではなく非空辺種類ごとに一度だけ行い、勝ち辺を一つ発見した時点で停止する。勝ち辺が存在しないことを証明する場合だけ全初手辺を走査する。`first_move_results.csv`には勝ち辺発見までに調べた辺だけを保存する。

- `edge_index`
- `start_id`、`end_id`
- `start_char`、`end_char`
- `edge_count`
- 勝敗
- 相手の残存辺インスタンス数
- 追加探索状態数

`exact_runs.csv`には`decision_status`、調査済み初手辺種類数、全走査したか、最初に見つけた勝ち辺を保存する。早期終了時の勝ち・負け初手数は調査済み部分だけの値であり、全初手の分布ではない。

## CLI

生成済みRuntimeDictionaryはファイルを直接指定する。文字数やseedを再入力せず、隣接metadataから辞書サイズとseedを取得する。

```bash
python src/experiments_exact.py \
  --runtime data/dictionaries/D100_L2-12_seed0.runtime.json \
  --timeout-sec 120 \
  --output-dir results/exact_edge_D100
```

共通語彙順位を保持する最大RuntimeDictionaryの先頭D語を使い、タイムアウトまでDを増加させる経路も追加した。

```bash
python src/experiments_exact.py \
  --runtime-prefix data/dictionaries/D10000_L2-12_seed0.runtime.json \
  --size-start 100 \
  --size-step 50 \
  --timeout-sec 120 \
  --output-dir results/exact_growth
```

`RuntimeDictionary.to_edge_dictionary(word_count=D)`は、単語文字列を完全解析へ渡さず、既存の`word_start_ids`と`word_end_ids`からD語接頭辞の辺数とactive maskを構築する。複数seedの最大RuntimeDictionaryを列挙した場合は、同じDで全seedがタイムアウトした時点で停止する。

複数ファイルも`--runtime`の後へ列挙できる。旧JMdict／records入力は互換用に残すが、抽出直後にRuntimeDictionary、EdgeDictionaryへ変換してから解析する。

## テストと比較

- 辺がない状態、`ん`辺だけの状態、相手を詰ませる状態を検証
- 同一自己ループ辺が1本なら勝ち、2本なら負けになることを検証
- 多重辺を含む小規模fixtureで、旧word-mask再帰と全開始文字の勝敗が一致
- 初手結果にword／word IDが存在しないことを検証
- 辺別結果の`edge_count`合計が辞書語数と一致
- Runtimeファイルを文字数条件なしでCLI指定できることを検証
- 勝ち初手辺を発見した直後に未調査辺を探索しないことを検証
- 負けを証明するときは全初手辺を走査することを検証
- RuntimeDictionaryのD語接頭辞辺数が、同じD語から独立構築した辺数と一致することを検証
- `--runtime-prefix`によるD増加がタイムアウト時に停止することを実データで確認

## 変更前の全初手走査との比較

D100 L2-12 seed0を解析した。

- 辺インスタンス数: 100
- 異なる辺種類数: 91
- 探索状態数: 425
- memo数: 425
- 解析時間: 0.000473秒
- タイムアウト: なし
- 先手勝ち: 真
- 勝ち初手: 43語相当
- 負け初手: 57語相当
- `ん`終端: 16語相当
- 初手結果行: 91
- 初手結果の`edge_count`合計: 100
- word／word ID列: なし

同じD100読み一覧を旧word-mask再帰でも確認し、勝ち初手は同じ43だった。探索状態数は手の列挙順と早期returnの影響を受けるため、方式間で同数になることは要件にしていない。

D200 L2-12 seed0も5秒・100万状態制限内で完了した。

- 辺インスタンス数: 200
- 異なる辺種類数: 175
- 探索状態数・memo数: 493,512
- 解析時間: 0.432121秒
- タイムアウト: なし
- 勝ち初手: 78語相当
- 負け初手: 122語相当
- 初手結果の`edge_count`合計: 200

早期終了後のD100、D200、D300（seed0）では次の結果になった。最大D500 RuntimeDictionaryの接頭辞を使い、勝ち辺を一つ発見した時点で停止している。

| D | 判定 | 探索状態数 | 解析時間 |
|---:|---|---:|---:|
| 100 | win_found | 1 | 0.000007秒 |
| 200 | win_found | 1,283 | 0.001012秒 |
| 300 | win_found | 52,914 | 0.048271秒 |

タイムアウト停止確認では制限を0.01秒とし、D100、D200を完了後、D300の10,941状態でタイムアウトして`stop_reason=all_seeds_timed_out`となった。時間値は性能保証ではなく通し確認結果である。

## 残っている問題

- 完全解析の状態数は依然として指数的に増えるため、D10000の完全解析が可能になるわけではない。
- 辺の多重度が大きいほど混合基数コードは大きな整数になるが、Python任意精度整数で正確性は維持される。
- 探索順序はstart/end ID順であり、状態数削減のための手の並べ替えは未実装である。
- 早期終了を既定にしたため、全勝ち初手数や文字別勝率を得るには診断用の`stop_on_first_win=False`による全走査が必要である。
- 反復深化、置換表、HybridAgentとの接続は次段階で扱う。
