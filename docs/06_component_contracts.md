# 06. 部品契約と分割レビューの資料索引

- 初回照合: 2026-09-03、実装基準 `d43fb2f`
- 作業: Issue #35（改善②）
- 共通処理の配置更新: Issue #37（改善③）。C08・C10の資料を追加し、12ジョブの区分を維持する。

## 1. 契約の読み方

ここでの契約は、部品を接続・レビューするための現行境界の説明です。**現行実装の観測であり、要求変更の承認や、全入力に対する正しさの保証ではありません。** 各文書を単独で渡す場合も、この区別を維持してください。

各部品の文書には、責務、呼び出し側の前提、入出力、空結果・例外・副作用、対象外、対応テストを記載します。「呼び出し側の前提」は、部品が入力検証してくれるという意味ではありません。型注釈やdataclassも実行時のschema検証ではありません。

要求・決定の根拠とS-01〜S-08は[現行仕様の照合表](05_current_specification.md)を参照します。未解決事項はそのまま引き継ぎます。新しい差を見つけた場合も、実装に合わせて要求を消さず、照合表へ根拠と必要な判断を追加します。

## 2. 12ジョブへの割り当て

各ジョブに「自分の契約＋実装＋対応テスト＋必要な依存契約＋関連する要求・未解決事項」を渡します。文書のリンク先は自動で入力に含まれるわけではないため、資料を準備する側が該当内容を添付してください。

| Job | 主たる契約 | 実装・テストの入口 | 主な依存契約 |
|---|---|---|---|
| 01 | [C01 Models](contracts/01_models.md) | [models.py](../scripts/models.py)、[Report test](../tests/test_report.py)など | 利用部品の生成・消費箇所 |
| 02 | [C02 GitHub API](contracts/02_github_api.md) | [github_api.py](../scripts/github_api.py)、[test](../tests/test_github_api.py) | なし |
| 03 | [C03 Collector](contracts/03_collector.md) | [collector.py](../scripts/collector.py)、[test](../tests/test_collector.py) | C01、C02 |
| 04 | [C04 Parser](contracts/04_parser.md) | [parser.py](../scripts/parser.py)、[test](../tests/test_parser.py)、[fixture](../tests/fixtures/workflow_mixed.yml) | C01 |
| 05 | [C05 Scanner](contracts/05_scanner.md) | [scanner.py](../scripts/scanner.py)、[test](../tests/test_scanner.py) | C01〜C04 |
| 06 | [C06 Resolver](contracts/06_version_resolver.md) | [version_resolver.py](../scripts/version_resolver.py)、[test](../tests/test_version_resolver.py) | C01、C02 |
| 07 | [C07 Report](contracts/07_report.md) | [report.py](../scripts/report.py)、[test](../tests/test_report.py)、[fixtures](../tests/fixtures/) | C01、C05、C06 |
| 08 | [C08 audit](contracts/08_audit.md) | [audit.py](../scripts/audit.py)・[test](../tests/test_audit.py)、[audit_pipeline.py](../scripts/audit_pipeline.py)・[test](../tests/test_audit_pipeline.py) | C01〜C03、C05〜C07 |
| 09 | [C09 本番Workflow](contracts/09_audit_workflow.md) | [audit.yml](../.github/workflows/audit.yml)、[test](../tests/test_audit_workflow.py) | C08 |
| 10 | [C10 Limited dry-run](contracts/10_limited_dry_run.md) | [limited_dry_run.py](../scripts/limited_dry_run.py)・[test](../tests/test_limited_dry_run.py)、[dry_run_support.py](../scripts/dry_run_support.py)・[test](../tests/test_dry_run_support.py)、対応Workflow | C02、C04、C06〜C08 |
| 11 | [C11 Organization dry-run](contracts/11_organization_dry_run.md) | [organization_dry_run.py](../scripts/organization_dry_run.py)、[test](../tests/test_organization_dry_run.py)、対応Workflow | C02、C03、C05〜C08、C10の共通API余裕判定 |
| 12 | 文書間の整合性 | [企画](01_project_proposal.md)、[設計](02_system_design.md)、[WBS](03_wbs.md)、[ADR](04_adr.md)、[照合表](05_current_specification.md)、[運用書](operations_ja.md)・[English](operations.md)、[README](../README.md)、[開発ルール](../AGENTS.md) | C01〜C11の関連箇所 |

Job 12は資料全部を一度に渡さず、要求、方式決定、運用、完了記録の順に小分けにします。C01〜C11も必要箇所を重複投入して構いません。fixtureは単体テストの入力・期待値、[reports](../reports/)は実行時の観測結果として区別します。

補助Workflowの担当は、[認証smoke](../.github/workflows/github-app-auth-smoke-test.yml)がJob 09、[Scanner Gate](../.github/workflows/scanner-gate-smoke-test.yml)がJob 05、[Resolver Gate](../.github/workflows/version-resolver-gate-smoke-test.yml)がJob 06、[Report Gate](../.github/workflows/report-generator-gate-smoke-test.yml)がJob 07です。固定期待値・外部環境の変化は単体テストと分けて確認します。

## 3. 接続で落とせない確認

| 接続 | 確認する契約 |
|---|---|
| Collector → Scanner | directory 404、本文404、例外の違い。取得成功したWorkflow数と対象repository数 |
| Parser → Resolver | source位置・ref・subpathを保持。`raw`は元行全文ではない |
| Scanner / Resolver → Report | usageとresolutionは重複数まで対応。C08の共通処理が両warningsを結合。Report builderを直接使う側にも同じ責任がある |
| Report → audit → Workflow | ローカル2ファイルの書き込み、CLI終了、artifact転送、Git commitは別段階 |
| audit → dry-run | 本番の部分失敗許容と各Gateの合格条件を区別。終了0と人手受入完了は同義ではない |

個別レビューの出力には、契約ID、根拠となるコード・テスト、入力例、期待結果と実際の差、未解決ID、他部品へ確認する事項を含めます。最後にその要約で境界を照合し、疑問のある箇所だけ原文を再投入します。要約だけで不具合の確定や「問題なし」の保証をしません。

## 4. 更新と検証

1. 境界を変えるIssue／PRでは、自部品と直接の呼び出し元・先の契約を確認する。
2. 要求変更には決定根拠、挙動変更には対応テストを付け、関係する契約と照合表を同じPRで更新する。
3. 契約の「代表テスト」は網羅性の証明ではない。テスト名と実際のassertionを読み、保証を広げない。
4. status表示順などの共通方針は照合表に置き、契約には境界で必要な内容と参照だけを置く。
5. Markdownのリンク・表・図と差分を確認する。APIを呼ぶlive Gateの実行は文書の表示検証とは別の作業である。

契約書を追加するだけでデータ検証・原子的書き込み・認証制限などが実装されるわけではありません。処理を共通化する際は、先に各呼び出し側の契約差を確認してください。
