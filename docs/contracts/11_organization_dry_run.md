# C11. Organization dry-run

現行境界の観測であり、要求への適合認定ではありません。[資料索引・更新方針](../06_component_contracts.md)を参照してください。

## 責務と依存

[organization_dry_run.py](../../scripts/organization_dry_run.py)はinstallation inventory、既定Filterでの全対象scan、catalog重複照会、API余裕を確認し、人手レビュー用の証拠を生成します。[C03](03_collector.md)、[C05](05_scanner.md)、[C08の共通処理](08_audit.md)、[C07の保存処理](07_report.md)を接続します。SummaryもC08、APIは[C02](02_github_api.md)に依存します。API余裕計算・不足理由は[C10の共通判定](10_limited_dry_run.md#共通api余裕判定)を利用し、例外型は`OrganizationDryRunError`を維持します。

## 入出力と前提

| 操作 | 契約 |
|---|---|
| `run_organization_dry_run(api, *, output_directory, expected_repositories_path)` | Report、visible / eligible / excluded repository名、ref種別件数、Resolver統計を持つ`OrganizationDryRunResult` |
| `validate_rate_limit_headroom(telemetry)` | `max(1000, requests * 10)`以上なら`None`、未観測・不足は`OrganizationDryRunError` |
| `append_organization_summary(path, result, telemetry)` | audit統計と人手確認待ちのSummaryを追記。resultの検証は再実行しない |
| `main(argv=None, *, environ=None)` | `--api-url` / `--output-directory` / `--expected-repositories`、token、任意のSummary path |

既定のinventoryは[organization_repositories.txt](../../tests/fixtures/organization_repositories.txt)。空行と`#`で始まるコメント行を除き、名前をcasefold順にsortします。空inventoryは不合格。名前の重複を集合に変換して除去する処理ではありません。

## 検証の順序と意味

1. installationを一度列挙し、visibleの名前列とinventoryの名前列をcasefoldして比較する。不一致ならscan前に停止する。
2. 既定Filterでarchived / forkを除外し、`FALSE_NEGATIVE_SAMPLE`の全repositoryがeligibleに含まれるか確認する。
3. `scan_repositories()`で再列挙せずscanし、C08の`resolve_scan_result()`で解決・warnings結合・Report生成を行う。同じ呼び出しから得たResolver統計を使う。
4. `catalog_lookups == summary.unique_actions`を確認し、ref種別件数とAPI余裕を確認する。
5. Report2ファイルとevidence JSONを保存して返す。

ref種別が0件の場合は`not_observed`であり、その種別のテスト合格ではありません。sampleのeligible確認も、Workflowを漏れなく検出できた証明ではありません。

## 出力・成功・失敗

出力は`organization-dry-run.md` / `.json`と`organization-dry-run-evidence.json`。evidenceは独自の`schema_version: 1`、`gate_state: human_review_pending`を持ち、visible / eligible / excluded、scan統計、ref件数、lookup統計、API統計、標本の位置、高・中severityの候補を含みます。Report JSONのschemaとは別です。

**partial errorsだけを理由にこのvalidatorを失敗させる検査はありません。** 他の検査を満たせばCLIは0で終了しますが、人手で誤検出・見落としを確認するGateは未完了です。evidenceを書いただけで受入完了にはしません。

検証違反は`OrganizationDryRunError`、API・I/O等の失敗は呼び出し側へ伝播します。CLIはtokenなし、または`GitHubApiError` / `OrganizationDryRunError` / `OSError` / `TypeError` / `ValueError`で1、正常完了で0。不正引数はargparseの終了2。environ指定時はそのMappingを使います。

API GET・fixture読込・Reportとevidence保存・Summary追記があり、Git commitはありません。Reportの後にevidenceを書くため、途中のI/O失敗で一部だけ残り得ます。検証前の失敗でも、以前から存在するファイルを削除する処理はありません。

[対応Workflow](../../.github/workflows/organization-dry-run.yml)はmanualのみ、read-only App tokenでcheckoutし、単体テスト後にCLIを実行します。`if: always()`で証拠をuploadし、ファイルなしはwarn、保持7日。artifactの存在とGateの通過を区別します。本番・限定dry-runとは別のconcurrency groupです。

## レビュー資料と未解決事項

[test_organization_dry_run.py](../../tests/test_organization_dry_run.py)の`test_audits_inventory_once_and_writes_human_review_evidence`、`test_inventory_mismatch_stops_before_scanning`、`test_summary_marks_absent_ref_kinds_as_not_observed`、[Workflow test](../../tests/test_organization_dry_run_workflow.py)を渡します。

`test_partial_upstream_failure_remains_available_for_human_review`はpartial errorsがあっても人手確認用evidenceを生成すること、`test_failed_quota_gate_precedes_report_writes`はAPI余裕判定の不合格時にReportを新規保存しないことを確認します。共通処理とAPI余裕判定の資料はC08・C10から添付してください。

[S-04](../05_current_specification.md#s-04rate-limit閾値warning)、[S-06](../05_current_specification.md#s-06数百repositoryとkpiの検証根拠)、[S-08](../05_current_specification.md#s-08errorsへの収録範囲)はこのGateの通過で解決しません。Resolver・Summaryの残る仕様差はC06・C08から引き継ぎます。
