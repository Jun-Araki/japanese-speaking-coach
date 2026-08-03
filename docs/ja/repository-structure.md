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
├── docs/                      恒久的ドキュメント — 何を作るか・どう作るか
│   ├── ja/                    日本語版。こちらが正。先に編集する
│   └── en/                    英語版。ja/ に合わせて更新する
├── config/
│   └── thresholds.toml        検証の閾値。コードに直値を埋め込まない
├── .steering/                 作業単位のドキュメント。作業ごとに1ディレクトリ
│   └── YYYYMMDD-タイトル/      requirements.md, design.md, tasklist.md
├── app/                       Streamlit の画面。1画面のみ
│   └── audio_check.py         iOS Safari の録音・自動再生の確認用。**使い捨て**、結果を記録したら消す
├── dialogue/                  (予定) 会話ノード
├── correction/                (予定) 訂正ノードと検証
├── retrieval/                 (予定) Chroma への登録と検索
├── nlp/                       (予定) SudachiPy の分かち書き、語彙レベル判定
├── evals/                     (予定) 評価スクリプト、ベースライン、実行記録
├── api/                       (予定) FastAPI アプリケーション
└── data/                      (予定)
    ├── evaluation/            評価データ120件の JSON — 公開成果物
    ├── grammar/               自作の文法リファレンス10本
    ├── recordings/            学習者の音声 — git 管理外、個人情報
    └── sessions/              セッションの書き出し — git 管理外、個人情報
```

## 配置のルール

- **`docs/` に個別の作業内容を書かない。** 作業固有の記述は `.steering/YYYYMMDD-タイトル/` に置く
- **学習者の発話・音声を含むものはすべて git 管理外。** `data/evaluation/` に入れてよいのは一般化した文だけで、特定個人の発言をそのままコミットしない
- **書籍や記事からの転記は公開しない**（`Sample/` は無視設定）。このリポジトリは公開されており、転記した内容を公開する権利はこちらにない
- **`PLAN.md` は git 管理外。** 契約・ビザ・応募先などの個人情報を含む。**公開ドキュメントからリンクしない**（リンク切れになる）
- 図表は関連するドキュメントの中に直接書く。`diagrams/` ディレクトリは作らない
