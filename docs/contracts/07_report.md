# C07. Report生成

現行境界の観測であり、要求への適合認定ではありません。[資料索引・更新方針](../06_component_contracts.md)を参照してください。

## 責務と依存

[report.py](../../scripts/report.py)は[C01](01_models.md)の値を正規化・集計し、Markdown / JSONを生成・保存します。API照会、version再判定、Git差分の判定・commitは担当しません。

## 入出力と呼び出し側の前提

| 操作 | 入力 → 出力 | 副作用 |
|---|---|---|
| `build_audit_report(scan_result, resolutions)` | ScanResultとresolution iterable → AuditReport | なし |
| `render_markdown(report)` | 正規化したAuditReport → 末尾改行付き文字列 | なし |
| `render_json(report)` | 同じAuditReport → schema_version付きJSON文字列 | なし |
| `write_reports(report, *, markdown_path, json_path)` | AuditReportと出力先Path → `None` | 親directory作成、2ファイル上書き |

呼び出し側は[C05](05_scanner.md)と[C06](06_version_resolver.md)のwarningsを結合してScanResultに入れます。builderはResolverのwarningsを自動で取得しません。

builderは`Counter(resolution.usage)`と`Counter(scan_result.usages)`を比較します。順序は違ってよいが、値と重複数の対応が必要です。不足・無関係なusage・重複数の違いは`ValueError`です。それ以外の全フィールドやcatalog整合性を検証するschema validatorではありません。

## 集計と出力

- findingはresolutionごとに1件、errorはScanResultのwarningごとに1件。warningsのdedupはしない。
- repository / Workflow件数はScannerの値を引き継ぐ。usage数はfindingsの数、unique ActionsはAction repositoryのcasefold単位で数える。
- severityはstatusから割り当てる。`INVALID_REF`はHIGHで「⛔ Invalid references」に独立表示する。表示順と対応は[照合表第4章](../05_current_specification.md#4-reportの現行表示)を参照する。
- findingsはstatus、source repository、workflow、行番号、Action repository、refのkeyでsortする。文字列のcasefoldと原表記による比較を含む。同一keyの要素は入力順が残るため、矛盾する手作りデータの全順列に対する同一出力を保証しない。
- JSONのtop levelは`schema_version: 1`、`summary`、`findings`、`errors`。公開keyは[C01](01_models.md)で確認する。
- 空結果でもsummary・各区分・Errorsを出力する。Markdownセルはbackslash・pipe・改行を処理するが、任意HTML向けの汎用sanitizerではない。

## 書き込みと失敗

既定出力は`reports/github-actions.md`と`reports/github-actions.json`。日時を生成して本文へ追加しません。rendererは渡されたモデルを使用し、独自に再集計しません。

書き込みはMarkdown、JSONの順で、2ファイルを原子的に更新する処理ではありません。JSON書き込みで失敗するとMarkdownだけ更新済みの場合があります。出力先は呼び出し側が別々の適切なpathを渡します。`OSError`や不正なモデルによる例外は呼び出し元へ伝播し、rollbackしません。ファイルが存在するだけでは今回の実行成功を意味しません。

## レビュー資料と未解決事項

[test_report.py](../../tests/test_report.py)の`test_rejects_missing_or_unrelated_resolutions`、`test_rendering_is_deterministic_for_shuffled_input`、`test_empty_report_matches_expected_snapshots`、`test_writes_both_report_files_from_same_model`を確認します。[期待Markdown](../../tests/fixtures/expected_report.md)・[期待JSON](../../tests/fixtures/expected_report.json)、[Report Gate](../../.github/workflows/report-generator-gate-smoke-test.yml)も資料です。代表テストの入力範囲を超える保証を付けません。

上流404のfindingがあってもErrorsが0になる現行動作と元の要求との差は[S-08](../05_current_specification.md#s-08errorsへの収録範囲)です。日時をGit管理reportへ入れない方針と、Job Summaryへ出す[S-07](../05_current_specification.md#s-07job-summaryの実行日時)は別に扱います。
