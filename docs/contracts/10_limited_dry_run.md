# C10. Limited dry-run

現行境界の観測であり、要求への適合認定ではありません。[資料索引・更新方針](../06_component_contracts.md)を参照してください。

## 責務と依存

[limited_dry_run.py](../../scripts/limited_dry_run.py)は固定された3repositoryと404注入fixtureのGateを検証します。実repositoryは[C08 audit](08_audit.md)の`run_audit()`、fixtureは[C04 Parser](04_parser.md)からC08の`resolve_scan_result()`へ渡し、[C07 Report](07_report.md)で保存します。実repositoryとfixtureのResolver cacheは独立しています。API統計は[C02](02_github_api.md)を使います。

## 入出力と前提

| 操作 | 契約 |
|---|---|
| `run_limited_dry_run(api, *, output_directory, fixture_path)` | `LimitedDryRunResult(repository_report, fixture_report)`を返す。既定outputは`reports`、fixtureは[limited_dry_run.yml](../../tests/fixtures/limited_dry_run.yml) |
| `validate_rate_limit_headroom(telemetry)` | 条件を満たせば`None`、未観測・不足は`LimitedDryRunError` |
| `append_limited_summary(path, result, telemetry)` | audit SummaryとGate項目を追記。呼び出し側はGateを通過したresultを渡す |
| `main(argv=None, *, environ=None)` | `--api-url` / `--output-directory`、tokenと任意のSummary pathを受け取る |

対象repo、既知finding、行番号、ref、statusはコードの`SELECTED_REPOSITORIES` / `REAL_EXPECTED_FINDINGS` / `FIXTURE_EXPECTED_FINDINGS`を入力条件として扱います。汎用の任意3repo検査ではありません。`fixture_path`の差し替えはライブラリ引数で、CLI引数にはありません。

## 処理と合格条件

1. include Filterで対象3repoを監査し、実repository用Markdown / JSONを保存する。
2. 対象repo数が3、reportのErrorsが0、finding keyの集合が期待集合と一致することを確認する。
3. sample-repo-cのWorkflow directoryを`ref=main`で別途照会し、404であることを確認する。
4. fixture本文を解析し、**live上流情報**で解決する。fixture用Markdown / JSONを保存し、finding keyの集合を比較する。
5. 観測remainingが`max(1000, requests * 10)`以上であることを確認する。等しい場合は合格。

finding keyはsource repository、workflow、行番号、Action repository、ref、statusの6項目です。集合比較なので同一keyの重複数やkey外のフィールド一致は保証しません。実repository reportにはErrorsゼロ確認がありますが、fixture reportには独立したErrorsゼロ確認がありません。

## 共通API余裕判定

[dry_run_support.py](../../scripts/dry_run_support.py)は両dry-runの計算と不足理由を担当する純粋関数群です。Job 10の資料としてレビューし、[C11 Organization](11_organization_dry_run.md)にもこの節を渡します。

| 操作 | 契約 |
|---|---|
| `required_rate_limit_remaining(telemetry)` | `ApiTelemetry`から`max(1000, requests * 10)`を返す。検証とSummaryが同じ計算を使う |
| `rate_limit_headroom_error(telemetry)` | remaining未観測なら`rate limit remaining was not observed`、不足なら`insufficient API rate limit headroom: remaining=…, required=…`。条件を満たせば`None` |

API照会・保存・例外送出を行わず、渡された統計だけを使います。入力の型や件数の範囲検証はしません。既存の`validate_rate_limit_headroom()`が不足理由を各dry-run固有の例外に変換し、CLIが従来どおり捕捉します。閾値の定義元は共通moduleで、既存の両dry-run moduleからも定数名をimportできます。

## 出力・失敗・副作用

出力は`limited-dry-run.md` / `.json`と`limited-dry-run-fixture.md` / `.json`の4ファイル。各検証より前に保存する段階があるため、不合格でもファイルが残り得ます。存在だけでGate通過と判断しません。API GET・ローカル保存・Summary追記があり、Git commitはしません。

ライブラリは検証違反を`LimitedDryRunError`として送出し、API・I/O等の失敗も伝播します。CLIはtokenなし、または`GitHubApiError` / `LimitedDryRunError` / `OSError` / `TypeError` / `ValueError`で1、完了で0。不正引数はargparseの終了2です。environ指定時はそのMappingを使います。

[対応Workflow](../../.github/workflows/limited-dry-run.yml)はmanualのみ、read-only App tokenでcheckoutし、単体テスト後にCLIを実行します。`if: always()`で証拠artifactをuploadし、ファイルなしはwarn、保持7日です。upload成功はGate合格を意味しません。本番とは別のconcurrency groupです。

## レビュー資料と未解決事項

[test_limited_dry_run.py](../../tests/test_limited_dry_run.py)の`test_known_repositories_and_404_fixture_match_expected_reports`と`test_rate_limit_headroom_rejects_missing_or_low_remaining`、[Workflow test](../../tests/test_limited_dry_run_workflow.py)を渡します。Fake APIのテストとlive Gateを区別し、外部repoや上流版の変化による不一致を直ちに実装不具合とは決めません。

[共通判定test](../../tests/test_dry_run_support.py)は閾値ちょうどの合格、下限とrequest比例、各例外型・文言を確認します。`test_failed_quota_gate_keeps_reports_written_before_the_check`はAPI余裕判定の不合格でも4つのReportが残る順序を確認します。

この余裕確認は[S-04](../05_current_specification.md#s-04rate-limit閾値warning)の本番warningの代替決定ではありません。固定入力の通過で[S-06](../05_current_specification.md#s-06数百repositoryとkpiの検証根拠)の検出率を保証しません。[S-08](../05_current_specification.md#s-08errorsへの収録範囲)のErrors収録要求も未解決です。Resolver・Summaryの残る仕様差はC06・C08から引き継ぎます。
