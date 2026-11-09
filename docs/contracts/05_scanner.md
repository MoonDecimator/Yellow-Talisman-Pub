# C05. Scanner

現行境界の観測であり、要求への適合認定ではありません。[資料索引・更新方針](../06_component_contracts.md)を参照してください。

## 責務と依存

[scanner.py](../../scripts/scanner.py)は[C03 Collector](03_collector.md)と[C04 Parser](04_parser.md)を接続して[C01 ScanResult](01_models.md)を作ります。バージョン比較・Report生成は担当しません。通信・fatal判定は[C02](02_github_api.md)に依存します。

## 入出力と呼び出し側の責任

| 操作 | 入力 → 出力 | 呼び出し側の前提 |
|---|---|---|
| `scan(api, policy)` | APIとFilter → `ScanResult` | installationを列挙できるAPIを渡す |
| `scan_repositories(api, repositories)` | RepositoryInfoのiterable → `ScanResult` | 対象を事前に選別する。この関数は再列挙・再フィルタ・dedupしない |
| `main(argv=None)` | CLI → 終了値、JSON Lines、stderr | tokenは`WATCHTOWER_TOKEN` |

`scan_repositories()`は入力をtupleとして保持し、その順でrepositoryを処理します。usagesはsource repositoryのcasefold、workflow pathのcasefold、行番号の順でsortします。同じsort keyの要素を任意入力順から完全に正規化する保証はありません。

## 件数・空結果

- `repositories_scanned`は渡された対象repository数。directory取得に失敗したrepositoryも含み、取得成功数ではない。
- `workflows_scanned`は本文を取得できたWorkflow数。外部usageが0のWorkflowも含む。
- usagesは抽出した参照ごとに保持し、warningsは回復可能な取得失敗を保持する。
- 対象0件は0件の正常結果。usagesが空でも、warningsの有無を別に確認する。

例えば対象1repoのdirectory取得が503で最終的に失敗すると、repo数1、Workflow数0、usages空、repository単位warning1件の結果を返します。

## 失敗と副作用

repository処理中の回復可能なAPI失敗は`workflow_path=None`のwarningにして次へ進みます。Collectorから戻った本文単位warningsも保持します。fatal API失敗は再送出します。**最初のinstallation列挙失敗は、このrepository単位のcatchの外**であり全体へ伝播します。

Parserの想定外の例外、応答形状の`TypeError` / `KeyError`等を一律に部分失敗へ変換しません。全体停止条件の要求差は[S-05](../05_current_specification.md#s-05全体停止するapiエラーの範囲)です。副作用はAPI GETとCLI出力。ライブラリ関数はReportファイルやGitを操作しません。

## CLI

`--api-url`、繰り返し可能な`--exclude`、`--include-archived`、`--include-forks`を受け付けます。`--include`はありません。成功時はusageの`to_dict()`を1行ずつstdoutへ、warningsと統計をstderrへ出して0を返します。API例外を捕捉すると1、token欠落・不正引数はargparseの`SystemExit(2)`です。`--help`はtokenなしで終了できます。[S-01](../05_current_specification.md#s-01設定ファイルとoverride-schema)の設定ファイルは読みません。

## レビュー資料と確認点

[test_scanner.py](../../tests/test_scanner.py)の`test_repository_5xx_is_non_fatal_partial_failure`、`test_repository_auth_failure_is_fatal`、`test_scans_previously_enumerated_repositories_without_listing_again`が代表例です。[Scanner Gate](../../.github/workflows/scanner-gate-smoke-test.yml)はlive環境での別検証です。件数を成功率に読み替えないこと、[S-06](../05_current_specification.md#s-06数百repositoryとkpiの検証根拠)の検出率を保証しないことを確認します。
