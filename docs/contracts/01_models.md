# C01. 共有データモデル

現行境界の観測であり、要求への適合認定ではありません。[資料索引・更新方針](../06_component_contracts.md)を参照してください。

## 責務と依存

[models.py](../../scripts/models.py)は、部品間で渡す値とJSON用の表現を定義します。API呼び出し、分類、集計、ファイル保存は担当しません。

## 型と受け渡し

| 型 | 生成 → 消費 | 意味 |
|---|---|---|
| `RepositoryInfo` | Collector → Filter / Scanner | `full_name`、`default_branch`とarchived / fork / private属性 |
| `WorkflowFile` | Collector → Parser | repository、path、取得した本文 |
| `ActionUsage` | Parser → Resolver / Report | 1つの外部参照。source、workflow、1始まりの行番号、raw、Action repository、subpath、ref、kind |
| `CollectionWarning` | Collector / Scanner / Resolver → Report | 部分失敗。`workflow_path=None`はrepository単位の位置 |
| `ScanResult` | Scanner → audit / Report | usages、warnings、対象repository数、取得Workflow数 |
| `SemanticVersion` | Resolver内部・catalog | major / minor / patchを整数で比較する値 |
| `ActionCatalogEntry` | Resolver → resolution | 最新候補と取得元。`repository_available`はrefの実在保証ではない |
| `VersionResolution` / `ResolutionResult` | Resolver → audit / Report | usageごとの分類と、その処理で生じたwarnings |
| `AuditFinding` / `AuditError` / `AuditSummary` / `AuditReport` | Report builder → renderer / Summary | 表示用行・エラー・集計と、それらをまとめた値 |

## 呼び出し側の前提

- 型注釈に沿った値を渡す。dataclassは`frozen=True, slots=True`だが、型・文字列形式・非負件数・行番号の正当性をコンストラクタで検証しない。
- `ActionUsage.kind`は文字列で、Parserは`github_action` / `reusable_workflow`を生成する。`RefKind`、`VersionStatus`、`AuditSeverity`は別のenumである。`VersionStatus.INVALID_REF`は最新安定候補より大きい数値refがTag / Branchともに存在しなかった場合の分類で、他のref全体の実在確認を保証しない（Issue #40）。
- `latest_stable` / `latest_version` / `source`は`None`を取り得る。空文字列への置換や最新扱いをせず、Resolverの分類結果と併せて読む。
- `AuditReport`を直接生成するとsummaryとfindingsの整合性検査を通らない。集計が必要な呼び出し側は[C07](07_report.md)のbuilderを利用する。

## シリアライズの境界

`ActionUsage.to_dict()`はdataclassの名前をそのまま使います。一方、`AuditFinding.to_dict()`は`workflow_path → workflow`、`line_number → line`、`action_repository → action`、`ref_kind → ref_type`へ変換し、enumは値の文字列にします。`AuditError`も`workflow_path → workflow`へ変換します。両形式を同じschemaとみなしません。

`AuditSummary.to_dict()`はseverity / statusのペア列を辞書にします。同名keyの重複を独立した件数として保持する形式ではありません。Report JSONの`schema_version`は[C07](07_report.md)が付与します。

## 空結果・例外・副作用

空tupleは有効な容器です。その意味は生成する部品が決めます。dataclassを作れたことは「監査成功」ではありません。外部I/Oはありません。型違反などを独自のAPIエラーへ変換する機能もありません。

## レビュー資料と確認点

- [Parser test](../../tests/test_parser.py)の`test_preserves_raw_reference_and_source_fields`でActionUsageの実際の生成値を確認する。
- [Report test](../../tests/test_report.py)の`test_json_has_schema_version_and_matches_normalized_report`、[JSON fixture](../../tests/fixtures/expected_report.json)で公開keyを確認する。Models専用テストファイルはない。
- [C05](05_scanner.md)の件数、[C06](06_version_resolver.md)のcatalog、[C07](07_report.md)の集計を必要部分だけ添付する。
- [S-03](../05_current_specification.md#s-03参照の実在確認とcurrentの意味)、[S-08](../05_current_specification.md#s-08errorsへの収録範囲): `CURRENT`やErrorsの値から、未決の要求を充足したと推論しない。
