# リポジトリ構造定義書

**この文書は日本語版が正。** 変更したら [`../en/repository-structure.md`](../en/repository-structure.md) も更新する。

> **薄く書く方針。** ディレクトリは作った順に追記する。*(予定)* は未作成。

```
japanese-speaking-coach/
├── CLAUDE.md                  開発プロセスの規約（日本語）
├── README.md                  公開の入口（英語）
├── pyproject.toml             依存とツール設定（ruff / mypy / pytest）
├── uv.lock                    依存の固定。**コミットする**
├── .env.example               必要な環境変数。.env は決してコミットしない
├── llm.py                     **提供元を選ぶ唯一の場所。** ここ1行で Gemini ⇄ Anthropic を差し替える
├── docs/                      恒久的ドキュメント — 何を作るか・どう作るか
│   ├── ja/                    日本語版。こちらが正。先に編集する
│   └── en/                    英語版。ja/ に合わせて更新する
├── config/
│   └── thresholds.toml        検証の閾値。コードに直値を埋め込まない
├── .steering/                 作業単位のドキュメント。作業ごとに1ディレクトリ
│   └── YYYYMMDD-タイトル/      requirements.md, design.md, tasklist.md
├── app/                       Streamlit の画面。1画面のみ
│   ├── main.py                会話画面。**Community Cloud の起動ファイルはこれ。恒久的に固定**
│   ├── corrections.py         会話終了時の一括訂正。**発話順に返す。並列数は上限つき**
│   ├── continuous.py          押さずに話す連続リッスン。**`CONTINUOUS_VOICE=0` でボタンに戻る**
│   ├── limits.py              1日のトークン・音声合成の上限と共有コード。**呼ぶ前に数えて拒否する**
│   └── theme.py               CSS と注意書き。**合成音声である旨・音声の限界の文言もここ**
├── dialogue/                  会話ノード
│   ├── scenes.py              場面・レベルの定義。**glossary.md §3・§4 が正本**
│   └── reply.py               `reply()`。相手役のプロンプトと1〜2文の制限
├── correction/                訂正ノード
│   ├── engine.py              `check()` と `check_with_retrieval()`。構造化出力を**自前で解析**し、書式の適合も返す
│   └── validation.py          検証ノード。**生成のあとに走る Python**（2回目の生成ではない）
├── graph/                     LangGraph。**画面も API もここを通る**
│   └── correction_graph.py    retrieve → correct → validate の3ノード。**検証③は載せない**（採否で不採用）
├── api/                       FastAPI。`GET /health` `POST /chat` `POST /check`
│   └── main.py                **Docker の入口。**Community Cloud では起動しない（1プロセス1エントリのため）
├── speech/                    音声
│   └── voice.py               書き起こしと合成。**書き起こしは学習者の誤りを消すことがある**（architecture.md）
├── tests/                     pytest。**モデルを呼ぶテストは書かない**（生成文には固定の正解がない）
├── retrieval/                 文法リファレンスの検索
│   ├── chunks.py              **節ごとに割る**（1本まるごと1チャンクにしない）
│   └── index.py               埋め込みと Chroma。**索引は起動時にメモリ上へ作る**（永続化すると古くなる）
├── Dockerfile                 API のコンテナ。**CPU 版 torch を明示**（PyPI 版は CUDA 2GB を引く）
├── compose.yaml               API と画面の2サービス
├── requirements.txt           デプロイ先が読む依存
├── requirements-no-retrieval.txt  **無料枠に載らなかったときの差し替え先**
├── nlp/                       日本語の語処理
│   ├── tokenize.py            SudachiPy の分かち書き。**日本語は空白で語を切らない**ので必須
│   ├── frequency.py           語の難易度の段階。BCCWJ の語彙表から**被覆率で切る**
│   └── level.py               `level_check()`。返答が学習者のレベルを超えていないか
├── evals/                     評価スクリプト、ベースライン、実行記録
│   ├── runs/                  測定1回ぶんの実行記録 JSON
│   ├── rater/                 第二採点者の採点キットと採点結果
│   ├── script.py              遵守率を測るための固定台本。**評価データを使わない**
│   ├── level_compliance.py    返答の語彙レベルの測定（1発目と再生成後の2つ）
│   ├── restage.py             **保存済みの実行記録に検証を後から当てる。API 呼び出しゼロ**
│   └── retrieval_measure.py   `score_min` の決定（10件）と当たり率（20件）。**両者は別集合しか読まない**
└── data/
    ├── evaluation/            評価データ120件の JSON — 公開成果物
    │   └── candidates/        検証前の候補。items.json の材料であって正本ではない
    ├── grammar/               自作の文法リファレンス8本。**評価データを引用しない**（pytest で固定）
    └── frequency/             BCCWJ の語彙表と段階の表 — **git 管理外**。再配布の可否が
                               明示されていないため同梱しない（取得は `python -m nlp.frequency --build`）
```

**`recordings/` と `sessions/` は作らない（2026-08-16 決定）。** 旧版はここに
「学習者の音声」「セッションの書き出し」を置く予定として書いていたが、
**何も保存しないことにした**ため、どちらもディスク上に生まれない
（[architecture.md](architecture.md) の「保存しないという決定」）。

## 配置のルール

- **`docs/` に個別の作業内容を書かない。** 作業固有の記述は `.steering/YYYYMMDD-タイトル/` に置く
- **学習者の発話・音声を含むものはすべて git 管理外。** `data/evaluation/` に入れてよいのは一般化した文だけで、特定個人の発言をそのままコミットしない
- **書籍や記事からの転記は公開しない**（`Sample/` は無視設定）。このリポジトリは公開されており、転記した内容を公開する権利はこちらにない
- **`PLAN.md` は git 管理外。** 契約・ビザ・応募先などの個人情報を含む。**公開ドキュメントからリンクしない**（リンク切れになる）
- 図表は関連するドキュメントの中に直接書く。`diagrams/` ディレクトリは作らない
