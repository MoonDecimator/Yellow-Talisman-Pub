# C09. 本番Workflow

現行境界の観測であり、要求への適合認定ではありません。[資料索引・更新方針](../06_component_contracts.md)を参照してください。

## 責務と実行前提

[audit.yml](../../.github/workflows/audit.yml)は認証、[C08 audit](08_audit.md)の起動、artifact転送、中央reportの差分commitを担当します。version分類や集計をYAML内で再実装しません。

実行環境にはGitHub Appの`WATCHTOWER_APP_CLIENT_ID` Variableと`WATCHTOWER_APP_PRIVATE_KEY` Secret、必要なrepositoryへのinstallation access、中央repoへ書ける`GITHUB_TOKEN`の経路が必要です。App tokenで中央ソースもcheckoutするため、対象repoだけでなく中央repoへのread accessも必要です。設定手順は[運用書](../operations_ja.md)を参照します。

## 入口とjob間の契約

| 段階 | 入力・出力と権限 |
|---|---|
| 起動 | `workflow_dispatch`、日曜04:17 `Asia/Tokyo`のschedule。手動の通常運用は`main`を選択 |
| `audit` | `permissions: {}`。read-only App tokenを発行し、tokenでcheckout、`persist-credentials: false` |
| CLI | `WATCHTOWER_TOKEN`を渡し`python3 -m scripts.audit`を実行。フィルタ引数なし |
| upload | 成功後に2つのreportを`github-actions-audit-reports`へ保存。`if-no-files-found: error`、保持1日 |
| `commit-report` | `needs: audit`。中央repoを`ref: main`でcheckout、jobだけ`contents: write` |
| download | 同じartifact名から`reports`へ取得 |
| commit | 2つのreport pathをstage。差分がある場合だけcommitし`HEAD:main`へpush |

audit側checkoutには明示的な`ref: main`がありません。手動で別branchを選ぶとその実行refのソースが使われ得ますが、commit先は`main`です。「両jobが常に同じcommitをcheckoutする」と仮定しません。

## 成功・失敗・副作用

- 監査CLIが非ゼロ終了すると通常の後続uploadは実行されず、`commit-report`も成功依存を満たさない。
- CLIが0ならpartial errorsやoutdated findingsがあってもreportを転送・commitし得る。内容の合格判定を追加するGateではない。
- 差分なしは正常終了でcommit / pushを省略。差分の有無をcommit-reportのJob Summaryへ出す。
- artifactの取得、commit、push失敗はjobの失敗。push retry / rebase / rollbackをYAMLには実装していない。
- concurrency groupは`action-watchtower-audit`、`cancel-in-progress: false`。同じgroupの実行制御であり、他のwriterによるmain更新まで排他するものではない。
- 外部への書き込みはartifact・Summaryと中央reportのGit更新。対象repositoryへ更新PRやcommitは作らない。

## レビュー資料と限界

[test_audit_workflow.py](../../tests/test_audit_workflow.py)の`test_audit_uses_minimal_read_only_app_token`、`test_commit_job_has_scoped_write_and_changed_only_push`等を確認します。これらはYAML内の設定・文字列の検査で、GitHub側のinstallation設定やbranch rulesの実効性を証明しません。[認証smoke](../../.github/workflows/github-app-auth-smoke-test.yml)は実環境の別検証です。

[S-01](../05_current_specification.md#s-01設定ファイルとoverride-schema)のconfigは読みません。[S-07](../05_current_specification.md#s-07job-summaryの実行日時)の実行日時をSummaryへ追加する処理もありません。CLIの部分失敗・停止・Errorsに関する未解決事項は[C08](08_audit.md)から引き継ぎます。
