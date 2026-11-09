# 05. 現行仕様と実装の照合表

- 対象: `example-org/Yellow-Talisman` のPhase 1監査
- 初回照合日: 2026-09-03
- 実装の照合基準: `9b54442`
- 文書整理: Issue #33

この文書は、要求・決定と現行実装の対応を示す索引です。実装を観測しただけの事項と、決定済みの要求を区別します。差があることを理由に、要求を自動的に廃止したり、実装を正しいと認定したりしません。部品ごとの詳細な契約書や、全境界条件を網羅した不具合レビューではありません。

## 1. 文書の位置づけ

| 資料 | 役割と読み方 |
|---|---|
| [企画書](01_project_proposal.md) | 目的・非目的・当初の到達目標。概念例や未達の要求は、その旨を明示する |
| [設計書](02_system_design.md) | FR/NFR、全体構成、処理方針。元の計画との差は本書へリンクする |
| [ADR-001](04_adr.md) | Acceptedの方式選定と理由。実装の観測事実だけで上書きしない |
| [WBS](03_wbs.md)・Stage Issues | 導入時の作業・受入記録。チェック済みでも、将来構想の実装済み宣言にはしない |
| 本書 | 要求・実装・テスト・決定根拠の照合と、未解決事項の入口 |
| [部品契約と資料索引](06_component_contracts.md) | 部品の入出力・前提・失敗時の現行境界を説明。要求変更の承認とは区別する |
| [運用書（日本語）](operations_ja.md)・[English](operations.md) | 現行の操作・成功確認・復旧手順 |
| [README](../README.md)・[AGENTS.md](../AGENTS.md) | プロジェクトの入口と開発手順 |

記述の状態は次の意味で使います。

- **現行・根拠あり**: 実装に対応し、既存の要求・Issue・マージ済みPRに根拠がある。
- **現行実装の観測**: コードから確認した挙動。要求への適合や採用判断を単独では保証しない。
- **概念例／導入時の記録**: 説明や過去の作業順を示す。現在実行する設定のコピー元にしない。
- **将来構想**: 将来Phaseとして明示済みの機能。現在使える機能と区別する。
- **未解決**: 元の要求と現物の差、または検証根拠の不足があり、結論を確定していない。

文書同士が矛盾した場合は、関連Issue・PR・ADRを調べ、根拠と結論を記録します。AcceptedのADRを変更する必要がある場合は、[開発ルール](../AGENTS.md)に従い別途判断します。

## 2. 現在の提供範囲と根拠

**現行・根拠あり:** GitHub Appでアクセス可能な対象repositoryを読み取り、Workflowの外部参照を収集し、Release / Tagに基づくバージョン監査結果を中央reportに保存します。対象repositoryの変更、自動更新PR、自動mergeはPhase 1に含めません。[ADR-001](04_adr.md)が方式の根拠です。

Phase 1の運用引渡し・リリース完了はIssue #10とTracking #11に記録されています。WBSと設計書の受入チェック更新はPR #28、PR #29、PR #32を参照してください。これは各runの成功や全仕様の網羅的検証を保証するものではありません。

現在の処理は、[Collector](../scripts/collector.py) → [Parser](../scripts/parser.py)を含む[Scanner](../scripts/scanner.py) → [Resolver](../scripts/version_resolver.py) → [Report](../scripts/report.py)を[audit](../scripts/audit.py)が接続する構成です。共有データ型は[models.py](../scripts/models.py)、通信・retryは[github_api.py](../scripts/github_api.py)にあります。

Issue #37では、ScanResultからのversion解決・warnings結合・Report生成を[audit_pipeline.py](../scripts/audit_pipeline.py)へ、両dry-runのAPI余裕計算・不足判定を[dry_run_support.py](../scripts/dry_run_support.py)へ抽出しています。対象選定・保存・Gate判定は各入口が担当します。これは処理の配置変更であり、S-01〜S-08の解決や要求変更ではありません。境界は[C08](contracts/08_audit.md)、[C10](contracts/10_limited_dry_run.md)、[C11](contracts/11_organization_dry_run.md)を参照してください。

## 3. 設定と実行経路

| 入口 | 現在利用できる設定・動作 | 根拠 |
|---|---|---|
| Appのinstallation | 読み取り可能なrepositoryの範囲を決める。All / Selectedの選択は[README](../README.md)を参照 | [ADR第5章](04_adr.md#5-authentication-and-permission-decision)、Issue #2 |
| Actions Variable / Secret | `WATCHTOWER_APP_CLIENT_ID`、`WATCHTOWER_APP_PRIVATE_KEY` | [本番Workflow](../.github/workflows/audit.yml) |
| Actions実行環境 | 全Workflowは `[self-hosted, linux, x64]` を指定。該当labelを持つOnlineのLinux x64 runnerが必要。runnerには `bash` / `git` / `python3` / `gh` / `jq` と一般的なGNU/Linuxコマンドを用意する | [README Setup](../README.md#3-self-hosted-runner-を用意する)、[運用書](operations_ja.md#self-hosted-runner-の前提) |
| 本番 `audit.yml` | 日曜04:17 `Asia/Tokyo`のscheduleと`workflow_dispatch`。同じaudit処理を実行 | PR #26、[テスト](../tests/test_audit_workflow.py) |
| `python3 -m scripts.audit` | `WATCHTOWER_TOKEN`が必要。`--include` / `--exclude`は繰り返し指定可。`--include-archived` / `--include-forks` / `--api-url`も提供 | [実装](../scripts/audit.py)、[テスト](../tests/test_audit.py)、PR #23 |
| `python3 -m scripts.scanner` | 中間結果のJSON Linesをstdout、warning・統計をstderrへ出力。`--exclude` / archived / fork / API URLの引数を提供。`--include`は提供しない | [実装](../scripts/scanner.py)、PR #16 |
| `config/watchtower.yml` | ファイル・loader・schemaは未実装。`config/`にはplaceholderのみ | [設計書第8章](02_system_design.md#8-config設計)、本書S-01 |

本番Workflowはaudit CLIにフィルタ引数を渡しません。既定でarchived / forkを除外し、include / excludeの指定なしで動きます。CLIで可能な設定が、Actionsの手動実行フォームに用意されているとは限りません。`--help`の表示にtokenは不要です。

本番の`audit` jobはread-only App tokenでソースのcheckoutと監査を行い、reportをartifactにします。`commit-report` jobは`audit`の成功後に実行され、`main`をcheckoutしてartifactを取得し、reportの2ファイルだけを差分検出・commit・pushします。中央repositoryへの書き込みには`GITHUB_TOKEN`を使用します。通常の手動実行は`main`から行ってください。cronは設定上の予定時刻であり、実際の開始時刻はActions runで確認します。[実装](../.github/workflows/audit.yml)、PR #22

検証用Workflowは本番用と別にあります。

| Workflow | 役割 |
|---|---|
| [github-app-auth-smoke-test.yml](../.github/workflows/github-app-auth-smoke-test.yml) | App tokenの発行、private repositoryと指定Workflowの読み取り |
| [scanner-gate-smoke-test.yml](../.github/workflows/scanner-gate-smoke-test.yml) | 実環境の既知usageの収集確認 |
| [version-resolver-gate-smoke-test.yml](../.github/workflows/version-resolver-gate-smoke-test.yml) | 既知usageと上流情報による判定確認 |
| [report-generator-gate-smoke-test.yml](../.github/workflows/report-generator-gate-smoke-test.yml) | 実環境から生成したMarkdown / JSONの照合 |
| [limited-dry-run.yml](../.github/workflows/limited-dry-run.yml) | 限定repository・fixtureの検証、証拠artifactの保存 |
| [organization-dry-run.yml](../.github/workflows/organization-dry-run.yml) | repository一覧・標本・件数・API統計の検証、証拠artifactの保存 |

これらは手動検証用で、reportをGitへ自動commitしません。固定されたrepository・行番号・ref・最新majorやinventoryは導入時の検証条件を含みます。不一致が生じた場合は、実装不具合と外部環境の変化を切り分け、期待値変更の根拠を記録します。単体テストのFake APIによる固定入力と、live APIを使うGateは別の検証です。

## 4. Reportの現行表示

**現行実装の観測:** [report.py](../scripts/report.py)と[対応テスト](../tests/test_report.py)におけるstatusの表示順・severityは次のとおりです。実装導入はPR #20を参照してください。

| 順番 | Status | Severity | Markdown詳細の区分 |
|---|---|---|---|
| 1 | `INVALID_REF` | high | Invalid references |
| 2 | `MAJOR_OUTDATED` | high | Major updates required |
| 3 | `UNRESOLVABLE` | high | Unresolvable and unknown references |
| 4 | `UNKNOWN_REF` | medium | Unresolvable and unknown references |
| 5 | `MINOR_OUTDATED` | medium | Updates available |
| 6 | `PATCH_OUTDATED` | low | Updates available |
| 7 | `FLOATING_BRANCH` | medium | Policy warnings |
| 8 | `SHA_PINNED` | info | Policy warnings |
| 9 | `CURRENT` | info | Current references |

findingsはstatusを第一のsort基準とします。severityだけの降順ではありません。元の企画書の7項目の相対順を維持し、元の一覧で順位未記載だった`UNKNOWN_REF`を未解決参照の区分に表示しています。Issue #40の対応では未来の数値ref不在を扱う`INVALID_REF`（high）を追加し、他の更新候補より前に表示します。

JSONのトップレベルは`schema_version: 1`、`summary`、`findings`、`errors`です。ScannerのJSON LinesとReportのJSONは別形式です。内部型と公開keyは[models.py](../scripts/models.py)、実際の期待出力は[fixture](../tests/fixtures/expected_report.json)を参照してください。

report本文には実行日時を含めず、2つの固定ファイルを変更時だけcommitします。auditのJob Summaryにはscan件数、severity / status件数、partial errors、API統計が出ます。report差分の有無は`commit-report`側のSummaryに出ます。実行日時はActions runの記録を確認しますが、Job Summaryへの出力要求を満たしたとは扱いません。この差は[未解決S-07](#s-07job-summaryの実行日時)です。

`CURRENT`はあらゆるrefの実在・安全性・互換性の証明ではありません。最新安定候補を超えるmajor / 完全SemVer refについてのみ実在するTagをAPI照会し、なければBranchを照会します。両方404なら`INVALID_REF`、同名Branchなら`FLOATING_BRANCH`です。それ以外の数値refやSHAの実在確認は未実施です。短縮SemVerの要求差はS-02、残りの実在確認はS-03を参照してください。

## 5. FR/NFRと実装の対応

この表はレビュー資料を探すための索引です。テストの存在をもって、その要件の全条件が検証済みとは判定しません。未解決欄がある行は、その差を含めてレビューします。

| 要求 | 現行の対応・注意点 | 実装 / テスト | 決定・導入根拠 |
|---|---|---|---|
| FR-01 列挙 | installationからpaginationで取得 | [API](../scripts/github_api.py)、[Collector](../scripts/collector.py) / [API test](../tests/test_github_api.py)、[Collector test](../tests/test_collector.py) | #3 |
| FR-02 フィルタ | archived / fork / include / exclude。設定ファイルとの差はS-01 | [Collector](../scripts/collector.py)、[audit](../scripts/audit.py) / [Collector test](../tests/test_collector.py)、[audit test](../tests/test_audit.py) | PR #16、PR #23 |
| FR-03 Workflow検出 | default branchのdirectory一覧・本文を取得。directory 404は正常な空結果 | [Collector](../scripts/collector.py) / [test](../tests/test_collector.py) | #3 |
| FR-04 uses抽出 | 行ベースParser。reusable workflowも抽出するが、呼び出し先本文を再帰走査しない | [Parser](../scripts/parser.py) / [test](../tests/test_parser.py) | PR #16、設計第11章 |
| FR-05 外部Action識別 | owner / repository / subpath / refを保持 | [Parser](../scripts/parser.py) / [test](../tests/test_parser.py) | #3 |
| FR-06 除外 | local・親相対・Docker参照を解析結果から除外 | [Parser](../scripts/parser.py) / [test](../tests/test_parser.py) | PR #16 |
| FR-07 上流情報 | stable Release優先、適切な候補なしならTags。cacheはResolverインスタンス内 | [Resolver](../scripts/version_resolver.py) / [test](../tests/test_version_resolver.py) | [ADR第6章](04_adr.md#6-version-resolution-decision)、#4 |
| FR-08 比較 | 9種のstatus（Issue #40で未来数値refの`INVALID_REF`を追加）。短縮SemVerと実在確認の残りはS-02 / S-03 | [Resolver](../scripts/version_resolver.py)、[Models](../scripts/models.py) / [test](../tests/test_version_resolver.py) | #4 |
| FR-09 Markdown | summary、status別詳細、errors。Errorsへの収録要求との差はS-08 | [Report](../scripts/report.py) / [test](../tests/test_report.py) | #5 |
| FR-10 JSON | schema_version付き、同じAuditReportから生成。errorsの収録範囲もS-08に関連 | [Report](../scripts/report.py)、[Models](../scripts/models.py) / [test](../tests/test_report.py) | #5 |
| FR-11 Summary | audit統計とcommit-reportの差分情報。実行日時の出力要求との差はS-07 | [audit](../scripts/audit.py)、[Workflow](../.github/workflows/audit.yml) / [audit test](../tests/test_audit.py)、[Workflow test](../tests/test_audit_workflow.py) | #6 |
| FR-12 差分commit | 固定reportの2ファイルに差がある場合だけcommit / push | [Workflow](../.github/workflows/audit.yml) / [test](../tests/test_audit_workflow.py) | [ADR第7章](04_adr.md#7-reporting-decision)、#6、#9 |
| NFR-01 Security | App read-onlyと中央writeを分離。Appの実設定はソースだけでは確認できない | [Workflow](../.github/workflows/audit.yml)、[API](../scripts/github_api.py) / [Workflow test](../tests/test_audit_workflow.py) | [ADR第5章](04_adr.md#5-authentication-and-permission-decision)、#2 |
| NFR-02 Determinism | 決定的sortと日時を含まない本文 | [Report](../scripts/report.py) / [test](../tests/test_report.py) | #5 |
| NFR-03 Scalability | pagination、dedup、telemetry。数百repoの保証はS-06 | [API](../scripts/github_api.py)、[Resolver](../scripts/version_resolver.py)、[Org dry-run](../scripts/organization_dry_run.py) / [test](../tests/test_organization_dry_run.py) | #4、#8 |
| NFR-04 Observability | warnings・errors・API統計。低remaining時のwarningはS-04、日時はS-07、Errors収録範囲はS-08 | [audit](../scripts/audit.py)、[Report](../scripts/report.py) / [audit test](../tests/test_audit.py) | #6 |
| NFR-05 Fault tolerance | 対象単位の回復可能なAPI失敗は継続、列挙失敗などは停止。4xx方針はS-05 | [API](../scripts/github_api.py)、[Scanner](../scripts/scanner.py)、[Resolver](../scripts/version_resolver.py) / [API test](../tests/test_github_api.py)、[Scanner test](../tests/test_scanner.py)、[Resolver test](../tests/test_version_resolver.py) | #6、PR #22 |
| NFR-06 Testability | API・解析・比較・描画を分離。Fake API / transportで検証 | [scripts](../scripts/) / [tests](../tests/) | 設計第3章、PR #16、PR #18、PR #20 |

### 障害時の現行動作

以下は[audit](../scripts/audit.py)、[Collector](../scripts/collector.py)、[Resolver](../scripts/version_resolver.py)、[API](../scripts/github_api.py)で確認した動作です。

| 場面 | 現行の扱い |
|---|---|
| `.github/workflows` directoryが404 | 空のWorkflow一覧。errorには数えない。Issue #3 / #7で正常ケースとされている |
| 一覧取得後にWorkflow本文が404 | 対象Workflowのwarningを残して継続し、reportのerrorsに反映 |
| 上流Release / Tags取得が404 | 該当usageを`UNRESOLVABLE`としてfindingsに残す。この経路だけではerrorsを増やさない。元のErrors収録要求との差はS-08 |
| 上流に数値比較用の候補がない | major / 完全SemVerは`UNRESOLVABLE`。上流取得可能ならSHAやbranchは別の分類規則を適用 |
| 対象単位の5xx・通信失敗がretry後も続く | 回復可能なAPI失敗としてwarningに記録し継続。Resolverでは該当Actionのusageを`UNRESOLVABLE`にする |
| 404以外の4xxがAPI層から返る | `is_fatal_api_error()`により全体を停止。設計上の表現との差はS-05 |
| installation repository列挙失敗 | 対象集合を得られないため全体失敗 |
| token未指定、auditが捕捉するAPI・出力等の失敗 | audit CLIは非ゼロ終了。引数不正はargparseの非ゼロ終了 |
| partial errorsを含む監査が完了 | audit CLIは0で終了し、report / Summaryでpartial errorsを表示 |
| 必要なreport commit / pushに失敗 | commit-report jobが失敗する |

`UNRESOLVABLE`の件数と`errors`の件数は別の指標です。上流404をfindingsだけに残す現行動作が、元のErrors収録要求を満たすかどうかは[未解決S-08](#s-08errorsへの収録範囲)として扱います。API retryは初回を含め最大3試行が既定で、429・5xx・rate-limitedな403・通信失敗を対象とし、`Retry-After`などを考慮します。低remaining時の運用判断とは区別します。

## 6. 未解決の仕様差

以下は本整理で解消済みと扱わない項目です。Issue #33の文書整備完了によって、実装済み・廃止決定済み・修正済みにはなりません。後続の判断・修正では、このIDを参照して結論と根拠を記録してください。

### S-01：設定ファイルとoverride schema

- **元の要求:** 設計FR-02はconfig制御、第8章は`config/watchtower.yml`と「v1でschemaだけ確保」を記載。
- **現物・根拠:** [audit CLI](../scripts/audit.py)とPR #23にinclude等はあるが、設定ファイル・loader・schemaはない。WBSはMVPのoverride延期を許すが、Phase 1でschema不要と決めた根拠とは異なる。
- **必要な判断:** CLIを正式な代替とする範囲、設定ファイル・schemaを実装するか延期するかを決める。現在の運用手順には未実装ファイルの作成を要求しない。

### S-02：短縮SemVerの扱い

- **元の要求:** 企画第7.3節は`@v7.0`を監査対象refとして列挙。
- **現物・根拠:** `parse_semver()`は短縮形を受け付けず、[test_rejects_prerelease_shortened_and_leading_zero_versions](../tests/test_version_resolver.py)がそれを確認する。静的分類されないrefはbranch照会へ進み、存在しなければ`UNKNOWN_REF`となる。
- **必要な判断:** 短縮形の数値比較を追加するか、監査対象として抽出する範囲と比較可能な形式を要求上明確に分けるかを決める。既存テストだけを理由に元の要求を消さない。

### S-03：参照の実在確認とCURRENTの意味

- **元の要求:** 企画第1章には「存在しないref」の検知例がある。
- **現物・根拠:** Issue #40で、最新安定候補より数値が大きいmajor tag / 完全SemVer refについては同名Git Tagの実在を確認する。不在なら同名Branchを確認し、両方なければ`INVALID_REF`、Branchのみなら`FLOATING_BRANCH`と判定する。上流取得不可時は`UNRESOLVABLE`。一方、最新以下の数値ref・SHA・subpathの実在確認は未実装で、`CURRENT`から全面的な実在・安全性・互換性は推論できない。
- **必要な判断:** 最新以下のmajor tag / 完全SemVer・SHAなどの実在確認範囲を別途決める。今回は未来の数値refによる検出漏れに限定した部分解消であり、S-03全体は未解決のままとする。

### S-04：rate limit閾値warning

- **元の要求:** 設計第21章はremainingが閾値以下ならwarningとする。
- **現物・根拠:** 本番[audit](../scripts/audit.py)はtelemetryを表示するが、閾値warning処理はない。両dry-runの`validate_rate_limit_headroom()`は、観測値なし・余裕不足を失敗にする。Issue #6はtelemetry、#7・#8は余裕確認を扱う。
- **必要な判断:** 本番にもwarningを設けるか、運用者確認で代替するかを決める。dry-runの失敗判定を本番warningの実装とみなさない。

### S-05：全体停止するAPIエラーの範囲

- **元の要求:** 設計第19章の停止条件は「API認証が全面的に401/403」などを例示。
- **現物・根拠:** [is_fatal_api_error](../scripts/github_api.py)は404以外の全4xxをfatalにする。対象単位の401/403、retryを使い切った429なども停止し、全面障害かどうかの判定はしない。[関連テスト](../tests/test_github_api.py)、PR #22に実装根拠がある。
- **必要な判断:** 現行の停止範囲を正式な運用方針とするか、処理対象・エラー種別に応じて狭めるかを決める。現行動作の記述と、要求を改訂する判断を分ける。

### S-06：数百repositoryとKPIの検証根拠

- **元の目標:** NFR-03は数百repo、企画第12章は95%以上の正常scan・Workflow検出100%を掲げる。
- **現物・根拠:** pagination・dedup・telemetryとOrg-wide Gateはあるが、固定inventoryや標本確認から数百repoの性能・検出率を一般化できない。件数だけでは正常取得率や見落とし率を計算できない。
- **必要な確認:** 対象規模・成功率の分母と失敗定義を定め、必要な負荷・網羅性検証の証拠を追加する。目標は維持し、検証済みの保証値としない。

### S-07：Job Summaryの実行日時

- **元の要求:** [企画第10.2節](01_project_proposal.md#102-毎回コミットしない)は「毎回の実行日時・スキャン件数は `$GITHUB_STEP_SUMMARY` に出力する」とする。Git管理するreport本文に日時だけの差分を入れない方針とは別の要求です。
- **現物・根拠:** [write_job_summary()](../scripts/audit.py)は件数・API統計を出力するが、実行日時は出力しない。[本番Workflow](../.github/workflows/audit.yml)もJob Summaryに実行日時を追加しない。Issue #6・PR #22は統計表示を扱うが、日時出力をActions runの記録で代替する明示的な決定は確認できていない。
- **必要な判断:** Job Summaryに実行日時を追加するか、Actions runの記録を正式な代替とするかを決める。現行の確認手順を記しただけで元の要求を廃止しない。

### S-08：Errorsへの収録範囲

- **元の要求:** [設計第16.5節](02_system_design.md#165-errors)は「アクセス不能・upstream 404・API失敗は必ず末尾へ出す」とする。
- **現物・根拠:** [Resolver](../scripts/version_resolver.py)は上流Release / Tags取得の404を捕捉して`UNRESOLVABLE`のfindingを返し、この経路ではwarningを生成しない。[Report](../scripts/report.py)のErrorsは収集・照会のwarningsから生成されるため、他のwarningがなければ上流404のfindingがあってもErrorsは0となる。Issue #5・PR #20にはfindings / errorsの保持方針があるが、上流404をErrorsから除外する明示的な決定は確認できていない。
- **必要な判断:** 上流404等をErrorsにも収録するか、findingsでの可視化を正式な代替とするかを決める。全体停止時を含むAPI失敗の表示範囲も明確にし、停止条件の判断はS-05と対応づける。現行のMarkdown / JSON / Summaryのerror件数を、元の収録要求への適合の証拠とはしない。

## 7. 文書更新時の確認

1. 変更する要求・観測事実・将来構想・未解決IDを特定する。
2. 仕様変更なら決定根拠を、実装変更なら対応するテストを記録する。
3. この照合表と関連する設計・運用・READMEを同じPRで更新する。
4. 過去の受入チェックは履歴として扱い、新たな検証完了を意味する更新をしない。
5. 通常操作は運用書へ、詳細な部品契約は[部品別文書](06_component_contracts.md)へ置き、同じ規則の独立した複製を増やさない。境界を変えるPRでは、関連する契約と要求の根拠も確認する。
