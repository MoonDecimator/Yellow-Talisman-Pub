# C03. Repository / Workflow Collector

現行境界の観測であり、要求への適合認定ではありません。[資料索引・更新方針](../06_component_contracts.md)を参照してください。

## 責務と依存

[collector.py](../../scripts/collector.py)はinstallationのrepository列挙・選別とdefault branchのWorkflow取得を担当します。本文の解析は[C04](04_parser.md)、監査全体の継続判断は[C05](05_scanner.md)が担います。依存は[C01](01_models.md)と[C02](02_github_api.md)です。

## 入出力と前提

| 操作 | 入力 → 出力 |
|---|---|
| `RepositoryCollector.list_repositories()` | API → `tuple[RepositoryInfo, ...]`、full_nameのcasefold順 |
| `eligible_repositories(policy)` | `RepositoryFilter` → 列挙結果のうち選択対象 |
| `RepositoryFilter.includes(repository)` | `RepositoryInfo` → bool |
| `WorkflowCollector.list_workflow_paths(repository)` | repository → 直下のfileかつ拡張子`.yml` / `.yaml`のpath tuple、casefold順 |
| `fetch_workflow(repository, workflow_path)` | repositoryとpath → `WorkflowFile`または404時の`None` |
| `collect(repository)` | repository → `(workflows, warnings)`の2つのtuple |

APIのrepository itemには`full_name`と`default_branch`が必要です。Workflow directory応答はlist、対象entryにはpathが必要です。取得はbranch名を指定し、commit SHAで全取得を固定する処理ではありません。呼び出し側は全fileが同一時点のsnapshotだと仮定しません。

## 選別の現行規則

- archived / forkは既定で除外。include指定があっても、それだけでこの除外を解除しない。
- includeが空なら名前による制限なし。full nameと短いrepo名の両方をcasefoldして照合する。
- excludeはfull nameまたは短いrepo名に**大文字小文字を区別する一致**で照合する。includeと同じ規則だと仮定しない。
- excludeに一致すればincludeより優先。名前による重複repositoryの除去はしない。
- 設定ファイル読み込みはこの部品の機能ではない。[S-01](../05_current_specification.md#s-01設定ファイルとoverride-schema)の要求差は未解決。

## 空結果と失敗

| 場面 | 呼び出し元へ返すもの |
|---|---|
| directoryが空、対象fileなし、directory 404 | `list_workflow_paths()`は`()`、`collect()`は`((), ())`。warningは生成しない |
| 本文404 | `fetch_workflow()`は`None`、`collect()`はそのpathのwarningへ変換して次へ |
| 本文の回復可能なAPI失敗 | `collect()`がwarningへ変換して次へ |
| 本文のfatal API失敗 | 再送出して中断 |
| directory取得の404以外の失敗 | `collect()`の外へ伝播。repository単位の扱いはScannerが決める |
| repository列挙・応答形状の失敗 | 空一覧へ置き換えず伝播。`KeyError` / `TypeError`等もあり得る |

fatalの分類は[C02](02_github_api.md)と[S-05](../05_current_specification.md#s-05全体停止するapiエラーの範囲)を参照。副作用はAPI GETで、ファイル保存・Git操作はしません。

## レビュー資料と確認点

[test_collector.py](../../tests/test_collector.py)の`test_exclude_takes_precedence_over_include`、`test_directory_404_is_no_workflows`、`test_file_404_is_recoverable_warning`、`test_file_5xx_is_recoverable_and_collection_continues`が代表例です。`collect()`のdirectoryエラーを本文エラーと同じcatch範囲だと読み違えないこと、include / excludeのcase差を確認します。
