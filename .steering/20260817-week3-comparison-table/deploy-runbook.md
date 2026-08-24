# 再デプロイ手順（Streamlit Community Cloud）— 2026-08-20 作成

**これは新規作成ではなく再デプロイである。** URL は既にある：https://nihongo-coach.streamlit.app/
（8/3 に作成済み、本番で会話まで確認済み）。**作り直すと URL を取り直しになる**ので、
アプリを消して作り直さないこと。

**起動ファイルは Settings から変更できない**（第1週 Day 1 の実測）。
現在の起動ファイルは `app/main.py` で、**ここは恒久的に固定する**。FastAPI を切り出したが、
**Community Cloud では FastAPI は動かさない**（1プロセス1エントリのため。アプリは同じプロセスで
グラフを呼ぶ）。

---

## 0. 先に直す2件（本体作業とは別。**当日気づくと詰む**）

- [x] **公開設定は完了（2026-08-21 確認）。** Settings → Sharing は
      **「This app is public and searchable」**（Community Cloud にはこの2択しかない。
      「Anyone with the link」は存在しない）。**スマホのシークレットタブで開けることを確認済み。**

> **`curl` で判定してはいけない。** `curl -sI https://nihongo-coach.streamlit.app/` は
> **public でも 303 で `/-/auth/app` へ飛ぶ。** Cloud は JavaScript も Cookie も持たない
> クライアントを認証側へ回すためで、**private の証拠にならない。**
> 2026-08-21 にこれで1時間ほど誤診した。**判定はブラウザのシークレットタブで行う。**
- [ ] **Python のバージョンを確認する。** Cloud 側は 3.14、手元の `.venv` は 3.12。
      **Advanced settings → Python version** で確認できる。下の依存はどちらでも解決する想定

## 1. Secrets（Cloud の Settings → Secrets に貼る）

```toml
GEMINI_API_KEY = "（~/.zshenv の値。リポジトリには絶対に置かない）"
ACCESS_CODE = "（会場で口頭で伝える1本。例: minna0913）"

# 任意。未設定なら app/limits.py の既定値（20万トークン / 5万文字 / 20ターン）が効く
DAILY_TOKEN_LIMIT = "200000"
DAILY_TTS_CHAR_LIMIT = "50000"
MAX_TURNS = "20"

# 任意。2026-08-22 に増えた3本。いずれも未設定で既定どおり動く
TTS_COOLDOWN_SECONDS = "60"   # 429 を受けたら何秒だまるか
CONTINUOUS_VOICE = "1"        # 0 で押して話す方式に戻る（会場の回線が WebRTC を通さないとき）
WARM_RETRIEVAL = "1"          # 0 で索引を起動時に作らず、必要になってから作る
```

**`ACCESS_CODE` を設定すると、アプリ側にコード入力画面が出る**（`app/main.py` の `render_gate`）。
**設定しなければ画面は出ない**ので、ローカルでは今までどおり素通しで動く。

## 2. 依存ファイル

**Cloud は `requirements.txt` を読まない**（2026-08-24 にビルドログで判明）。
`pyproject.toml` と `uv.lock` があるとそちらが優先され、ログに
`WARN: More than one requirements file detected` と出る。**依存を変えるときは
`pyproject.toml` を直して `uv lock` を実行すること。** `requirements.txt` の編集だけでは
デプロイに反映されない。

`requirements.txt` は **`pip install -r` と Docker イメージ**が読む。要点は2つ。

- **`--extra-index-url https://download.pytorch.org/whl/cpu` と `torch==2.13.0+cpu`。**
  PyPI の `torch` を Linux で入れると **CUDA 一式（cudnn・nccl・cusparselt・nvshmem・triton）が
  付いてきて約2GB**になる。GPU の無い無料枠でこれを引くと、**分単位かけたあとディスクで落ちる**。
  CPU 版なら約190MB
- **`fastapi` と `uvicorn` は入れていない。** Cloud では起動しないため。Docker 側に入れる

**インストール容量の目安：約300MB**（torch-cpu 190 ＋ SudachiDict 72 ＋ chromadb 24 ＋ streamlit 10）。
**加えて起動時に埋め込みモデルを約120MB ダウンロードする**（`intfloat/multilingual-e5-small`）。

## 3. 落ちたときの分岐（**先に決めておく**）

**ビルドが容量か時間で落ちたら、`requirements-no-retrieval.txt` の中身を `requirements.txt` に
上書きして再デプロイする。** 判断を当日に持ち越さない。

**その前に試す手が1つ増えた（2026-08-22）。ビルドではなく「起動」で落ちるなら `WARM_RETRIEVAL=0`。**
索引を起動時にバックグラウンドで作るようになったので、**誰も訂正を実行しなくても
毎回埋め込みモデル（約120MB＋torch）が載る。** 以前は「最初の訂正まで載らない」ので、
訂正に到達しないまま生き延びていたビルドがありえた。

- **効くのは起動時のメモリだけ。** 訂正を1回でも実行すれば結局載るので、**定常のメモリは変わらない**
- **失うのは速さだけ。** 1ターン目の訂正が15秒ほど遅くなる（会話終了時に1回だけ）
- **ビルド自体が落ちているなら効かない。** その場合は上の `requirements-no-retrieval.txt` へ

- **失うのは「訂正に添える出典」だけ。** `check_with_retrieval` は import 失敗を飲み込んで
  根拠なしで訂正を返し、`GET /health` は `retrieval.available = false` と理由を返す
- **公開する数字は1つも失われない。** 測定は手元の `evals/` で回しており、
  デプロイ先のビルドに依存していない
- **ただし、README が説明する製品より弱いものを配ることになる。**
  その場合は**アプリの画面にその旨を1行出す**こと。訪問者に気づかせる形にしない

## 4. デプロイ後に必ず確認する（5分）

- [ ] **自分のスマホで開く。** 会話が成立し、振り返りが読めるか（PC だけで終わらせない）
- [ ] `ACCESS_CODE` を設定したなら、**コード画面が出て、正しいコードで通る**か
- [ ] **注意書きが開始画面に出ている**か（外部送信・非保存・生成物である旨・連絡先）
- [ ] 1往復して**「End the conversation」を押し、振り返りに訂正が出典つきで出る**か。
      **2026-08-22 に訂正を会話終了時へ移したので、会話中には何も出ない**（出たら実装が違う）。
      出典が無いなら §3 の分岐に入っている
- [ ] **ターン上限に当たったときの表示**（20文で入力欄が閉じる）
- [ ] **マイクが繋がるか。** 繋がらなければ `CONTINUOUS_VOICE = "0"` にして押して話す方式へ。
      画面には「Starting the microphone…」が出たままになる
- [ ] **返事が読み上げられるか。鳴らなくても画面には何も出ない**（2026-08-22 の決定）。
      **鳴らないときは Cloud のログを見る**——`[speak] no audio for ...` に理由が出る。
      `429 Too Many Requests` なら無料枠の速度上限で、**故障ではない**

## 5. 状態（2026-08-22 現在）

- **音声は実装済み**（録音→書き起こし→会話、返事の読み上げ）。**ただし書き起こしが
  学習者の誤りを直すことがある**ので、画面に注意書きを出している（[design.md](design.md) §12）
- **訂正は会話終了時にまとめて実行する**（2026-08-22 変更）。会話中は 1 文も訂正しない。
  詳細は [応答速度の tasklist](../20260821-latency/tasklist.md)
- **音声は「鳴ればおまけ」。** 無料枠の速度上限に1人で当たることが実測で分かっており、
  **鳴らないことは想定内**（返事の文字は必ず出る）。
  [docs/ja/architecture.md](../../docs/ja/architecture.md)「音声合成は無料枠の速度上限に当たる」
- **未確認：実機のマイクで、返事の音声が自分のターンを終わらせてしまわないか。**
  エコー捨ては入れてあり pytest でも固定しているが、**本物のマイクとスピーカーの間で
  起きることは測れていない。デプロイ後の確認項目に入れること**
- **Docker はこの手順の対象外。** `fastapi` / `uvicorn` はそちらの入口

---

## 記録欄（デプロイ実施後に埋める）

| 項目 | 値 |
|---|---|
| 実施日 | |
| 使った requirements | `requirements.txt` / `requirements-no-retrieval.txt` |
| ビルド所要 | |
| 検索が有効か（`/health` 相当） | |
| スマホでの確認 | |
