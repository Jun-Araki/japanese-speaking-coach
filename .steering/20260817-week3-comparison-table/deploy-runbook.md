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

- [ ] **アプリが private になっている疑いを解消する。**
      `curl -sI https://nihongo-coach.streamlit.app/` が `/-/login` へ 303 で飛ぶ状態だと、
      **9/13 に会場でインドの参加者が自分のスマホから開けない。**
      Cloud の **Settings → Sharing → "Anyone with the link can view"** にして public に戻す。
      **アプリ内の共有コードは別物**（こちらは残す。§2-5 の「共有コード1本」）
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
```

**`ACCESS_CODE` を設定すると、アプリ側にコード入力画面が出る**（`app/main.py` の `render_gate`）。
**設定しなければ画面は出ない**ので、ローカルでは今までどおり素通しで動く。

## 2. 依存ファイル

**`requirements.txt` をそのまま使う。** 中身の要点は2つ。

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
- [ ] 1往復して**訂正が出典つきで出る**か。出典が無いなら §3 の分岐に入っている
- [ ] **ターン上限に当たったときの表示**（20文で入力欄が閉じる）

## 5. まだ無いもの

- **音声は未実装。** 9/13 に間に合わなければテキスト版のまま手渡す（応募開始は動かさない）
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
