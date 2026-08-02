6: 機能設計書 (functional-design.md) - CLIツール版

● Write(docs/functional-design.md)
　⎿　Wrote 647 lines to docs/functional-design.md
　　 # 機能設計書 (Functional Design Document)
　　 ## システム構成図
　　 ```mermaid
　　 graph TB
　　　　 User[ユーザー]
　　　　 CLI[CLIインターフェース]
　　　　 Commander[Commanderjs]
　　　　 TaskManager[TaskManager]
　　 … +637 lines (ctrl+o to expand)

● 2/6 機能設計書 (functional-design.md) - CLIツール版を作成しました。

　以下の内容を含んでいます：
　- システム構成図（Node.js CLIアーキテクチャ）
　- 技術スタック（Commander.js, Inquirer.js, chalk, cli-table3, date-fns, uuid）
　- データモデル定義（Task型にestimatedPriorityとstatusHistoryを追加）
　- コンポーネント設計（CLI Layer / Service Layer / Data Layer）
　- 優先度自動推定アルゴリズムの詳細設計
　　- 期限スコア：期限までの残り日数で0-100点
　　- 経過時間スコア：作成からの日数で0-100点
　　- ステータススコア：進行中は高得点、完了は0点
　　- 総合スコア：加重平均（期限50%、経過時間20%、ステータス30%）
　　- 70点以上でhigh、40-70点でmedium、40点未満でlow
　- ユースケース図とコマンドフロー図（Mermaid）
　- UI設計（テーブル表示、カラーコーディング、インタラクティブモード）
　- ファイル構造（.devtask/tasks.json, config.json）
　- エラーハンドリング、パフォーマンス最適化、セキュリティ
