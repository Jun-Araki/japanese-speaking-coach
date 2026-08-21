# 設計 — 応答速度の改善（2026-08-21）

## requirements.md からの変更点（先に書く）

設計中に 2 つ判明したので、要求を 1 つ取り下げ、受け入れ条件を 1 つ書き換える。

### 取り下げ：**3. 返答のストリーミング表示はやらない**

`dialogue.reply` は `checked_reply` を呼んでおり、そこには**生成後に走る 3 つの関門**がある。

1. `limit_sentences` — 2 文に切り詰める
2. `looks_japanese` — 日本語でなければ**作り直す**（8/12 に 90 件中 2 件、英語の推論が返った）
3. `level_check` — 学習者の語彙段階を超えていれば**作り直す**（＝**検証ノード2**）

**3 つとも全文が揃わないと判定できない。** ストリーミングすれば、関門が捨てるはずの文が
そのまま学習者の目に入る。とくに 3 は「難しすぎる語を見せない」ことが目的なので、
**見せてから直すのは、この機能を無効にするのと同じ**である。

返答生成は 1.56s と 4 項目中もっとも軽い。**1.2 秒の体感のために検証ノード2 を壊す取引は成立しない。**

### 書き換え：受け入れ条件 4

- 旧：「返答の最初の文字が 1 秒以内に画面に出ること」
- 新：**「学習者自身の文が 3 秒以内に画面に出ること」**

ストリーミングをやめても画面は固まらない。`render_input` は文字起こしのあとに
`history()` へ追加して `st.rerun()` するので、**学習者の発話は 2.87 秒で画面に出て、
返答はその 1.56 秒後に続く。** 「無反応の時間」は実際には 2.87 秒であり、
これは新条件で測れる。

## 所要時間の再計算

| 段階 | 現状 | 変更後 | 手当て |
|---|---|---|---|
| 文字起こし | 3.40s | **2.87s** | thinking を切る |
| 返答生成 | 1.56s | 1.56s | 手を触れない |
| 音声合成 | 4.34s | **0s（ブロックしない）** | 入力欄より後ろに描画（案 A） |
| 訂正 | 4.78s | **0s** | 会話終了時へ移動 |
| **入力可能になるまで** | **14.08s** | **4.43s** | |

受け入れ条件 1（6 秒以下）を満たす。**ストリーミング無しで届く。**

## 実装アプローチ

### 1. 訂正を会話終了時へ移し、並列で走らせる

**呼び出し位置。** `render_conversation` の `record_correction(...)` を削除し、
「End the conversation」を押した時点でまとめて実行する。

**訂正対象は `history()` から取る。** 学習者の発話は既にそこにあるので、
別のリストは持たない。

```python
sentences = [u.text for u in history() if u.speaker == "learner"]
```

**副次的な改善：現状は返答が失敗したターンの文が訂正されない**（`record_correction` が
`else` 節にあるため）。history から取れば、失敗の有無にかかわらず全文が訂正される。
振り返りの「You said N sentences」と実際の件数が一致するようになる。

**`end_session()` は scene と level を pop する。** 訂正はそれらを必要とするので、
**pop より前に確保する。**

**並列化。** `ThreadPoolExecutor` で `run_correction` を並べる。`executor.map` は
**入力順に結果を返す**ので、振り返りの並び順は現状と同じになる。

```python
workers = min(len(sentences), MAX_CORRECTION_WORKERS)  # 5
```

**ワーカー数を 5 で止める理由。** 実測は 5 並列で 5.55s（逐次 23.39s）。`max_turns()` は 20 なので、
上限まで話した会話では 4 波に分かれて約 22 秒かかる。**それでも逐次の約 95 秒よりは短い。**
無制限に広げないのは、20 本同時の Gemini 呼び出しが 429 を誘発し、
**遅くなるどころか訂正が丸ごと落ちる**ためである。受け入れ条件 3（8 秒以下）は
5 文の会話に対する条件であり、20 ターンの会話には適用しない。

**待ち時間の見せ方。** `st.spinner` に固定文言ではなく件数を出す
（「Checking your N sentences…」）。何を待っているのか分かる。

**失敗の扱いは現状のまま。** 1 文の訂正が失敗しても他を巻き込まない。
`run_correction` を包む try/except は `record_correction` から持ち越し、
失敗した文は `correction=None` で並びに残る（振り返りの「could not be checked」が既に対応している）。

### 2. スレッド安全性 — **`lru_cache` は並列初期化を防がない**

これは並列化に伴って新しく発生する問題であり、見落とすと Cloud で落ちる。

`retrieval/index.py` の `_model()` と `collection()` は `lru_cache(maxsize=1)` だが、
**キャッシュミスの判定はロックの外で起きる。** 5 スレッドが同時に初めて `search()` を呼ぶと、
**5 つとも SentenceTransformer を読み込もうとする。**
手元では 8.55s × 5 の無駄で済むが、**Community Cloud のメモリでは落ちる。**

**対策：初期化を `threading.RLock` で囲う。**

```python
_INIT_LOCK: Final = threading.RLock()

def _model() -> SentenceTransformer:
    with _INIT_LOCK:
        return _load_model()          # ここが @lru_cache(maxsize=1)

def collection() -> Any:
    with _INIT_LOCK:
        return _build_collection()    # ここが @lru_cache(maxsize=1)
```

**`Lock` ではなく `RLock` である理由。** `collection()` は内部で `embed_passages()` を呼び、
それが `_model()` を呼ぶ。同じスレッドが同じロックを二度取るので、
**`Lock` だと確実にデッドロックする。**

取得済みロックの取得は数十ナノ秒であり、20ms の encode に対して無視できる。

### 3. 起動時のウォームアップ

**`st.cache_resource` で 1 プロセス 1 回だけスレッドを起動する。**
Streamlit はスクリプトを毎回上から実行し直すので、モジュール直下でスレッドを起こすと
**再実行のたびに増える。** `st.cache_resource` はプロセス全体で 1 回しか実行されない。

```python
@st.cache_resource
def _warm_retrieval() -> threading.Thread:
    def load() -> None:
        try:
            from retrieval.index import collection
            collection()
        except Exception:   # retrieval 無しビルドでも会話は成立する
            pass
    thread = threading.Thread(target=load, daemon=True, name="warm-retrieval")
    thread.start()
    return thread
```

**置き場所は `_adopt_secrets()` の直後。** 鍵の解決より前に走らせる意味はなく、
描画より前に起こしておきたい。

**2 と組み合わせて初めて安全になる。** ウォームアップ中に「End」が押されると、
訂正スレッドは同じ `RLock` を待つだけで、二重読み込みにはならない。

**ワーカースレッドから `st.*` を呼ばない。** `run_correction` も `collection()` も
Streamlit に触らないので、`ScriptRunContext` の警告は出ない。
**結果の `st.session_state` への格納はメインスレッドだけで行う。**

### 4. 文字起こしの thinking を切る

`speech/voice.py` の `transcribe` の `generationConfig` に足す。

```python
"generationConfig": {"temperature": 0, "thinkingConfig": {"thinkingBudget": 0}}
```

**訂正パスではないので、公開数字への影響はない**（制約事項のとおり、
訂正側のモデルと thinking 設定には触れない）。

**書き起こしの質は確認してから入れる。** `docs/ja/architecture.md` に記録がある
2026-08-20 の 5 文（実際の学習者の誤りを合成音声にしたもの）を thinking あり/なしで
流し、**出力が一致することを確認**する。一致しなければこの項目は取り下げる。

### 5. TTS は案 A — 入力欄を音声の完成待ちにしない

**推奨どおり案 A を採る。** 案 B（ブラウザの `speechSynthesis`）は 9/13 の会場で
端末を選べないため無音になるリスクが読めない。

**やり方：音声の描画位置だけ先に確保し、中身は最後に入れる。**
Streamlit はスクリプトの実行に合わせて差分を送るので、
**入力欄が先に画面へ届き、音声はそのあと届く。**

```python
with st.chat_message("assistant"):
    with st.spinner("…"):
        answer = reply(scene, level, history())
    st.write(answer)
    audio_slot = st.empty()      # 位置だけ押さえる
...
render_input()                   # ここで入力欄が画面に出る
...
with audio_slot:                 # 最後に音声を流し込む
    speak(answer)
```

**レイアウトは変わらない。** `st.empty()` が場所を押さえているので、
音声要素は今までどおり返答の直下に入る。

**代償を明記する。** 音声の生成中（約 4.3 秒）に学習者が次の文を送ると、
Streamlit は実行中のスクリプトを止めて再実行する。**そのターンの音声は鳴らない。**
これは案 A が意図的に選ぶ取引である——**次を話せる状態のほうが、前の行の音声より価値が高い。**
返答テキストは既に画面にあるので、読めなくなるものは無い。

## 影響範囲

### コード

| ファイル | 変更 |
|---|---|
| `app/main.py` | 訂正の呼び出し位置、ウォームアップ、音声の描画位置 |
| `retrieval/index.py` | `RLock` による初期化の直列化 |
| `speech/voice.py` | `transcribe` に `thinkingConfig` |

**`graph/correction_graph.py`・`correction/` は触らない。** 訂正の中身は変えない
（受け入れ条件 5・6）。

### ドキュメント（**ja と en を同じコミットに入れる**）

`docs/ja/functional-design.md` は現状の実装を記述しており、変更で**食い違う**。

- 54 行目「訂正ノードは**毎ターン裏で回し**、結果は振り返りでのみ見せる」
- 166 行目「`corrections` — **毎ターン裏で溜めた**訂正結果」

**「毎ターン」ではなくなる**ので、両方を「会話終了時にまとめて並列で回す」に直し、
`docs/en/functional-design.md` の対応箇所も同じコミットで直す。

**なお「訂正は会話に割り込ませない」という原則自体は変わらない。**
むしろ今回の変更は、その原則が実装で守られていなかったのを守らせるものである。

### テスト

- `tests/test_voice.py` — `transcribe` の payload に `thinkingConfig` が入ることを固定する
- **新規 `tests/test_corrections_batch.py`** — 並列実行が (a) 入力順を保つ、
  (b) 1 件の失敗で他を巻き込まない、の 2 点。`run_correction` はスタブする（API を叩かない）

## 未解決として記録すること（今回は直さない）

**`tests/test_graph.py` は存在しない。** `graph/correction_graph.py` の冒頭は
「`tests/test_graph.py` が 2 つの経路を同じ出力に固定している」と書いているが、
そのファイルは無く、グラフを参照しているテストは `tests/test_api.py` だけである。
requirements.md の受け入れ条件 5 はこのテストの存在を前提にしていたので、**前提が誤っていた。**

**今回のスコープでは直さない。** 訂正の中身に触らない以上、この欠落が今回の変更で
悪化することはない。ただし**コメントが実在しないテストを指している**のは、
このプロジェクトが避けたい種類の食い違いなので、tasklist に別項目として積む。
