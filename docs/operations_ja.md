# Yellow-Talisman 運用ランブック

> **非公開版の運用記録です。** 以下は元の内部運用構成を説明するもので、公開用ソースに同じWorkflowや内部検証環境があるとは限りません。公開版の利用方法は [公開版の運用ガイド](public_operations.md) を参照してください。


## 1. 目的

この文書は、Phase 1 の本番監査を日常運用し、問題発生時に復旧するための手順をまとめたものです。

Yellow-Talisman は、GitHub App がアクセス可能なリポジトリを横断して GitHub Actions の参照を監査し、最新の監査結果を次の固定ファイルへ保存します。

- `reports/github-actions.md` — 人間が読むためのレポート
- `reports/github-actions.json` — 機械処理向けのレポート

実行日時入りの履歴ファイルは作りません。監査結果が変化した場合のみ固定ファイルを更新して commit し、過去の状態は Git の履歴から確認します。

## 2. 通常運用

本番用 workflow は `.github/workflows/audit.yml` です。

次の2通りで実行できます。

- GitHub Actions の cron による定期実行（日曜04:17 `Asia/Tokyo`の予定）
- `workflow_dispatch` による手動実行

通常の run では、監査を実行し、生成したレポートを artifact としてアップロードした後、内容に実質的な差分がある場合だけ2つの report ファイルを commit します。差分がない場合は run 自体は成功しますが、report commit は作りません。

### Self-hosted runner の前提

全 Workflow は `runs-on: [self-hosted, linux, x64]` を使用します。repository または Organization に、`self-hosted`、`linux`、`x64` の各 label を持つ Linux x64 runner が登録され、Online であることを確認してください。該当 runner がない場合、scheduled run / manual run とも Queued のまま開始されません。

runner では少なくとも `bash`、`git`、`python3`、`gh`、`jq` と、`base64`、`grep`、`sed`、`tr`、`wc` など一般的な GNU/Linux コマンドを利用できる必要があります。また GitHub、GitHub API、Actions の取得先へ HTTPS で到達できることを確認します。

## 3. 手動監査

必要なときに手動で監査する手順は次のとおりです。

1. GitHub で Yellow-Talisman リポジトリを開く。
2. **Actions** を開く。
3. **GitHub Actions audit** を選ぶ。
4. **Run workflow** を選び、本番ブランチ`main`から workflow を実行する。
5. `audit` と `commit-report` の両方が成功したことを確認する。

手動 Dispatch は通常運用で使用して問題ありません。ただし意図的に重複実行する必要はありません。workflow 側には concurrency 制御がありますが、同じ監査を同時に複数走らせても運用上の利点はありません。

## 4. 成功 run の確認

本番 run ごとに、次を確認します。

- workflow 全体が `Success` になっている
- `audit` が成功している
- `commit-report` が成功している
- audit summary に想定外の partial error が出ていない
- 生成された report 内容が変化した場合、`reports/github-actions.md` と `reports/github-actions.json` が更新されている
- 生成された report 内容が変化しなかった場合、不要な report commit が作成されていない

定期実行の確認では、run event が `workflow_dispatch` ではなく `schedule` になっていることも確認します。

## 5. レポートの読み方

まず `reports/github-actions.md` を確認します。

現行は存在しない未来の数値バージョン参照（`INVALID_REF`、high）を先頭に表示し、続いて`MAJOR_OUTDATED`、未解決参照（`UNRESOLVABLE` / `UNKNOWN_REF`）、minor / patch更新、policy warnings、`CURRENT`の順に詳細を表示し、末尾にErrorsを表示します。`INVALID_REF`は、最新安定版より新しい数値refが同名のTagにもBranchにも見つからなかった場合の判定です。その他のすべてのrefについて実在確認を保証するものではありません。全statusの順序とseverityの対応は[現行仕様の照合表](05_current_specification.md#4-reportの現行表示)を参照してください。

`UNKNOWN_REF`は企画時の優先リストには順位がありませんでしたが、現行では未解決参照の区分に表示されます。`CURRENT`からrefの実在・互換性・安全性を推論しないでください。また、`UNRESOLVABLE`の件数とErrors件数は同じではありません。どちらも確認します。

このレポートは監査結果であり、自動更新の指示ではありません。Phase 1 では target repository を修正せず、更新 PR の作成や merge も行いません。

スクリプトや将来の連携機能で構造化データが必要な場合は `reports/github-actions.json` を使用します。

## 6. レポート履歴

レポートのファイル名は意図的に固定しています。通常の run ごとに `github-actions-YYYY-MM-DD.md` のようなファイルを増やさないでください。

過去の監査状態を確認したい場合は、対象 report ファイルの Git 履歴を開き、確認したい commit を参照します。これにより、repository 上には最新状態だけを置きつつ、実質的に変化した過去状態を Git で保持できます。

## 7. 障害の見つけ方

本番監査が失敗した場合、GitHub Actions 上で失敗した workflow / job / step として確認できます。むやみに再実行を繰り返すのではなく、まず失敗した step から原因を追います。

確認材料として有用なのは次の情報です。

- workflow event (`schedule` または `workflow_dispatch`)
- 失敗した job と step
- audit summary
- API error / status 情報
- artifact が生成されたか
- `commit-report` より前で失敗したのか、`commit-report` 中に失敗したのか

Secret、token、private key の内容を Issue、ログ抜粋、トラブルシューティング記録へ貼り付けないでください。

## 8. トラブルシューティング

### 認証に失敗する

repository 設定に必要な GitHub App 構成が残っていること、GitHub App が意図した repository 範囲にインストールされていることを確認します。Private key の Secret が存在することは確認して構いませんが、値を表示してはいけません。

### 監査対象の repository が出てこない

まず GitHub App の installation scope を確認します。Yellow-Talisman が列挙できるのは App installation からアクセス可能な repository だけです。現在の本番 workflow では、既定の `RepositoryFilter` により archived repository と fork も除外されます。audit CLIには`--include` / `--exclude`がありますが、現在の本番workflowは引数を渡していません。`config/watchtower.yml`の読み込みも未実装です。設定の入口と要求との差は[現行仕様の照合表](05_current_specification.md#3-設定と実行経路)を参照してください。

### Workflow ファイルが検出されない

対象 repository の default branch に `.github/workflows/*.yml` または `.github/workflows/*.yaml` が存在することと、GitHub App が repository contents を読めることを確認します。

### Version resolution に失敗する

finding と API error 情報を確認します。上流 repository が特殊な tag 運用をしている、release が存在しない、ref が削除された、GitHub API が一時的に失敗した、などの可能性があります。解決できない参照を自動的に「安全」または「古い」と決めつけないでください。

### Report が commit されない

生成された report と既存 report に実質的な差分がない場合は正常です。本番 workflow は no-op commit を意図的に作りません。

差分があるはずなのに commit されなかった場合は、生成 artifact と `commit-report` job を確認し、差分そのものが生成されたか、差分検出が行われたかを切り分けます。

### Commit step が失敗する

Yellow-Talisman repository の workflow permissions と branch protection を確認します。Target repository を読む GitHub App credential は Read-only です。Report commit は Yellow-Talisman 自身の `GITHUB_TOKEN` 経路で行い、target repository への Write 権限で代用してはいけません。

### Scheduled run が出てこない

本番 workflow が default branch に存在し、`schedule` trigger が残っていることを確認します。あわせて GitHub Actions の履歴や repository 側設定を確認し、workflow が無効化されていないか、schedule 実行側の問題がないかを調べます。

`workflow_dispatch` で手動実行すると、schedule の問題なのか監査ロジック自体の問題なのかを切り分けられます。

## 9. 復旧手順

本番監査が正常でない場合は、次の順で復旧します。

1. 最後に成功した本番 run を確認する。
2. 原因が schedule、authentication、collection、version resolution、report generation、report commit のどこにあるかを切り分ける。
3. 原因となっている最小範囲の設定またはコードを修正する。
4. `workflow_dispatch` で本番 workflow を手動実行する。
5. 両方の job が成功したことを確認し、report と artifact を確認する。
6. `schedule` trigger は有効のままにし、次回の scheduled run も通常どおり成功することを確認する。

一般的なトラブルシューティング手段として GitHub App の権限を広げないでください。

## 10. Secret rotation

GitHub App の private key が漏えいした可能性がある場合、失効した場合、または計画的な credential 更新を行う場合は、次の手順で rotation します。

1. 可能であれば既存 key がまだ利用可能な状態で、GitHub App settings から新しい private key を発行する。
2. Yellow-Talisman の Actions Secret `WATCHTOWER_APP_PRIVATE_KEY` を、新しい private key の完全な内容で置き換える。key を source file、Issue、PR comment、log、command-line argument へ貼り付けない。
3. **GitHub Actions audit** を `workflow_dispatch` で手動実行し、`audit` と `commit-report` の両方が成功することを確認する。
4. 新しい key で repository enumeration と report generation が正常に行われることを確認する。
5. 動作確認が成功した後で、旧 GitHub App private key がまだ有効なら削除・失効させる。
6. 動作確認に失敗した場合は、可能なら既知の有効な key でサービスを復旧し、key material を露出させず原因を調査して rotation をやり直す。

漏えい疑いによる rotation では旧 key を信頼しないものとして扱い、新 key の設定・確認後できるだけ速やかに失効させます。旧 private key の内容を project documentation や troubleshooting record に残さないでください。

## 11. Security boundary

Phase 1 の権限境界は意図的に設計されています。

- GitHub App は target repository を読む
- Yellow-Talisman は target repository を変更しない
- Phase 1 の GitHub App に Contents Write を与えない
- report の commit は Yellow-Talisman repository 内に限定する
- credential を source file、command-line argument、生成 report、log に記録しない

将来の Phase で target repository への Write が必要になった場合は、Phase 1 の権限を黙って広げるのではなく、別の設計判断・Security 判断として扱います。

## 12. 関連文書

- `README.md` — 目的、setup、report の概要、プロジェクトの入口
- `docs/01_project_proposal.md` — 背景とスコープ
- `docs/02_system_design.md` — 詳細アーキテクチャと Security 設計
- `docs/03_wbs.md` — 実装および受入の WBS
- `docs/04_adr.md` — アーキテクチャ上の設計判断とその理由
- [現行仕様の照合表](05_current_specification.md) — 現行動作、実装・テストへの対応、未解決の仕様差
