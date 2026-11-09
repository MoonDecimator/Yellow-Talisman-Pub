# C08. auditオーケストレーション

現行境界の観測であり、要求への適合認定ではありません。[資料索引・更新方針](../06_component_contracts.md)を参照してください。

## 責務と依存

[audit.py](../../scripts/audit.py)は[C05 Scanner](05_scanner.md)と、[audit_pipeline.py](../../scripts/audit_pipeline.py)の共通処理、[C07 Report](07_report.md)の保存処理を接続します。共通処理は[C06 Resolver](06_version_resolver.md)からReport生成までを担当し、本番・限定dry-runのfixture・Organization dry-runが利用します。APIは[C02](02_github_api.md)、対象選別は[C03](03_collector.md)です。Git commit、token発行、Actions jobの権限設定は[C09](09_audit_workflow.md)が担当します。

## 入出力

| 操作 | 前提と正常時の動作 |
|---|---|
| `run_audit(api, policy, *, markdown_path, json_path)` | 呼び出し側がAPI・Filter・出力先を渡す。Reportを保存し、`AuditReport`を返す |
| `resolve_scan_result(api, scan_result)` | 収集済みの`ScanResult`を渡す。Reportと今回のResolver統計を持つ`AuditPipelineResult`を返す |
| `write_job_summary(path, report, telemetry)` | 集計済みReportとAPI統計を渡す。pathの親を作成し、Summaryを追記して`None`を返す |
| `main(argv=None, *, environ=None)` | CLI引数と環境 → 終了値。environを渡した場合、os.environとマージせずそのMappingを使う |

`run_audit()`はscan後に`resolve_scan_result()`を呼び、返されたReportを保存します。ライブラリ関数自身は環境変数を読まず、Job Summaryも書きません。

## 共通処理の境界

`resolve_scan_result()`は呼び出しごとに新しいResolverを作り、scan warningsとresolution warningsを結合してReport builderへ渡します。元のScanResultを変更せず、usageの重複数とScannerの件数を保持します。`AuditPipelineResult.report`は`AuditReport`、`resolver_telemetry`はその呼び出しの`ResolverTelemetry`です。呼び出しをまたいだcache共有はしません。

空usageでもscan warningsと件数を引き継ぎ、上流照会をしません。Resolverのpartial warningはReportへ引き継ぎ、全体停止する例外は捕捉せず伝播します。404をErrorsへ追加する等の分類変更は行いません。入力の妥当性を検証する入口ではなく、C01・C05の前提を満たすScanResultを呼び出し側が用意します。

共通処理の副作用はResolverによるAPI GETです。repository列挙、ファイル保存、Summary追記、環境変数読込、Gate判定は行いません。保存・検証の順序は[C10](10_limited_dry_run.md)・[C11](11_organization_dry_run.md)を含む各呼び出し元に残ります。

## CLIと終了

- `WATCHTOWER_TOKEN`が必要。`--api-url`、繰り返し可能な`--include` / `--exclude`、`--include-archived`、`--include-forks`を受け付ける。
- 成功するとReportを保存し、`GITHUB_STEP_SUMMARY`があればSummaryを追記する。完了統計はstderrへ出し、0を返す。
- partial errorsやoutdated findingsがあっても、監査が完了すれば0。0は「更新不要」「全repositoryの取得成功」ではない。
- tokenなしは1。不正引数はargparseの`SystemExit(2)`。`--help`はtoken不要。
- 実行・出力処理の`GitHubApiError`、`OSError`、`TypeError`、`ValueError`を捕捉して1を返す。`KeyError`等の全例外を同じ経路で処理する保証はない。

## Summary・副作用・失敗境界

Summaryは件数、severity / status集計、partial errors、API統計を追記します。呼び出し回数分追記されるため、同一pathへの繰り返し呼び出しは置換ではありません。requested permissionsの表示は実際のtoken権限を検査した結果ではありません。

副作用はAPI GET、Report保存、指定時のSummary追記、CLI出力です。Report保存後にSummaryが失敗した場合もCLIは1となり、先に書いたReportは取り消しません。保存の原子性は[C07](07_report.md)を参照します。

## レビュー資料と未解決事項

[test_audit.py](../../tests/test_audit.py)の`test_pipeline_combines_partial_warnings_before_rendering`、`test_partial_errors_are_non_fatal`、`test_cli_passes_repeatable_include_filter`、`test_job_summary_contains_counts_and_rate_limit_telemetry`が代表例です。Mockで呼び出し先を置き換えたテストを、API実接続の検証と混同しません。

[test_audit_pipeline.py](../../tests/test_audit_pipeline.py)ではusageの重複、両warnings、空scan、404と403、呼び出しごとのcache・統計を確認します。Job 08で共通処理をレビューし、Job 10・11にもこの境界を渡してください。

[S-01 設定](../05_current_specification.md#s-01設定ファイルとoverride-schema)、[S-04 閾値warning](../05_current_specification.md#s-04rate-limit閾値warning)、[S-05 停止範囲](../05_current_specification.md#s-05全体停止するapiエラーの範囲)、[S-07 実行日時](../05_current_specification.md#s-07job-summaryの実行日時)、[S-08 Errors収録](../05_current_specification.md#s-08errorsへの収録範囲)は未解決です。現在のCLIが提供しない設定やwarningを、本契約で追加したとは扱いません。
