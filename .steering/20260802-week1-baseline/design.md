# 第1週 設計

対応する要求: [requirements.md](requirements.md)

---

## 実装アプローチ

**テキストのみの縦スライスを1本通す。**抽象化は入れない。第3週に FastAPI と LangGraph へ
切り出すことは分かっているが、**今週その形に寄せない**——使われ方が確定する前の抽象化は
作り直しになる。関数を素直に呼び、モジュール境界だけ将来の分割に合わせておく。

```
Streamlit (app/)
   │  st.session_state に会話履歴
   ├──▶ dialogue.reply(scene, level, history) ──▶ Claude API ──▶ 1〜2文
   └──▶ correction.check(sentence, scene, level) ──▶ Claude API（構造化出力）
                                                        │
                                            会話中は表示せず session_state に溜める
                                                        ▼
                                                  終了時に review 表示
```

**訂正は毎ターン走らせるが、表示は終了時。** 今週は同期呼び出しでよい（並列化は第4週の
最適化枠。ここで先に非同期にすると数字の前後比較が取れなくなる）。

---

## 変更・追加するコンポーネント

| モジュール | 今週作るもの |
|---|---|
| `app/` | Streamlit 1画面。場面・レベル選択 → 会話 → 振り返りの状態遷移 |
| `dialogue/` | `reply()`。場面とレベルに応じた相手役プロンプト。1〜2文に制限 |
| `correction/` | `check()`。構造化出力。**ベースライン版もここに `baseline_check()` として置く** |
| `evals/` | 採点スクリプト、実行記録の書き出し |
| `data/evaluation/` | 120件の JSON |
| `data/grammar/` | 8本（今週は RAG に載せない。文章を書くだけ） |

`retrieval/` `nlp/` `api/` は今週作らない。

---

## データ構造

[docs/ja/functional-design.md](../../docs/ja/functional-design.md) の定義に従う。今週の範囲では：

**評価データ1件**（`data/evaluation/items.json` の配列要素）

```json
{
  "id": "eval-001",
  "scene": "greeting",
  "learner_sentence": "おはようです",
  "needs_correction": true,
  "corrected_sentence": "おはようございます",
  "reason_en": "The polite morning greeting is a fixed phrase.",
  "split": "dev"
}
```

**訂正の構造化出力**（`correction.check()` の戻り値）

```json
{
  "needs_correction": true,
  "corrected_sentence": "おはようございます",
  "reason_en": "The polite morning greeting is a fixed phrase.",
  "grounding_ids": []
}
```

`grounding_ids` は今週は必ず空配列。第2週に RAG を入れたときに埋まる。
**キーは最初から最終形にしておく**（後から増やすとデータの作り直しが発生する）。

**実行記録**（`evals/runs/YYYYMMDD-HHMM.json`）

```json
{
  "run_id": "20260806-0730",
  "implementation": "baseline",
  "model": "claude-sonnet-5",
  "prompt_version": "baseline-v1",
  "split": "test",
  "date": "2026-08-06",
  "detection_accuracy": 0.0,
  "over_correction_rate": 0.0,
  "format_compliance_rate": 0.0
}
```

---

## ベースラインの設計（今週の主役）

**素朴版 = 大規模モデルに1回投げるだけ。** 検証も RAG も形態素解析も無い。

- プロンプトは「この日本語を直して、理由を英語で教えて」相当の1回呼び出し
- **意図的に良くしようとしない。** 素朴版を丁寧に作り込むと比較表の差が縮み、
  第2週以降の実装の価値が見えなくなる。ただし**出力形式だけは同じ JSON に揃える**
  （形式が違うと採点コードが2本になり、そこが不具合の温床になる）
- 測るのは `detection_accuracy` / `over_correction_rate` / `format_compliance_rate` の3つ
- **評価用40件に対して1回だけ実行し、記録して封をする**

---

## 採点の設計

- **機械採点するのは `needs_correction` の一致だけ。**
  `corrected_sentence` は完全一致で採点しない（[docs/ja/glossary.md](../../docs/ja/glossary.md) §5）
- `format_compliance_rate` は**精度と分けて記録する**。JSON が壊れた／理由が日本語で
  返ったケースを精度の低下と混同しない
- **採点スクリプト自体に pytest を書く。** 採点の不具合はモデルの改善と区別がつかない
- 実行のたびに**評価用から5件を手で照合**する

---

## 影響範囲

- 既存コードなし（初回実装）
- [docs/ja/glossary.md](../../docs/ja/glossary.md) の閾値2つ（編集距離・レベル超過語彙）は
  今週の範囲外。第2週に確定させて glossary へ書き戻す
- `docs/ja/repository-structure.md` の *(planned)* 表記は、作ったディレクトリから外していく

---

## 判断が必要になったら

- **疎通確認（8/3）が失敗した場合** → 音声を諦めてテキスト方式に切り替える。
  PLAN.md §3「降ろす順番」の1番を第1週の時点で適用する。この判断は先送りしない
- **評価データ作成が3時間を大きく超える場合** → 90件に減らし、誤差の但し書きを厚くする
  （降ろす順番の3番）。**分割の比率は変えない**
- **テスター候補の前向きな返事が3人未満** → 第2週の頭に計画を見直す
