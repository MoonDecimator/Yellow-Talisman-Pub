# ADR-001: GitHub Actions の依存監査を中央集約方式で行う

- Status: **Accepted**
- Date: 2026-08-21
- Project: `example-org/Yellow-Talisman`
- Scope: Phase 1 architecture

本ADRは方式選定とその理由の記録です。Acceptedの決定を維持したまま、現行の設定・実装・テストへの対応と未解決の差を[現行仕様の照合表](05_current_specification.md)で管理します。Contextの事例は当時の出来事、versionの数値例は比較規則の説明であり、現在の最新版や監査結果の宣言ではありません。

---

## 1. Context

`example-org` 配下の複数リポジトリで GitHub Actions を利用しているが、Workflow 内で参照している Action のバージョンが古くなっても、それ自体では直ちに実行失敗しない場合がある。

実際に、`sample-repo-a` と `sample-repo-b` の Workflow で `actions/checkout@v3` が残っており、GitHub Actions 実行時に Node.js ランタイムの deprecation warning が表示されたことで初めて更新の必要性に気付いた。

この出来事から、次の問題が明確になった。

1. あるリポジトリで古い Action を発見すると、他のリポジトリにも同様の古い参照が残っていないか確認する必要がある。
2. リポジトリ数が増えるほど、人間による `.github/workflows/` の巡回確認は非効率になる。
3. Action の更新は継続的に発生するため、一度全リポジトリを確認しても問題は再発する。
4. 「現在の最新バージョン」を LLM や人間の記憶だけで判断するのは危険であり、GitHub 上の Release / Tag など実データを参照する必要がある。
5. 監査対象リポジトリに不要な Write 権限を与えずに済むことが望ましい。

そのため、Organization 全体の GitHub Actions 依存関係を継続的に監査する仕組みが必要になった。

---

## 2. Decision Drivers

今回の方式選定では、以下を重視する。

- 新しいリポジトリが増えても、監査設定の追加作業を極力発生させない
- Organization 全体の状態を一か所で確認できる
- private repository を含めて監査できる
- 監査対象リポジトリは原則 Read-only にする
- GitHub 上の実データを source of truth として version を判定する
- 定期実行と手動実行の両方を可能にする
- 監査結果を Git 履歴として残し、後から変化を振り返れるようにする
- 将来、自動更新 PR や通知へ拡張できる

---

## 3. Considered Options

### Option A: 人間が各リポジトリを定期巡回する

各リポジトリの `.github/workflows/*.yml` / `*.yaml` を人間が開き、`uses:` の参照バージョンを確認する。

#### Advantages

- 新しい仕組みを導入する必要がない
- 実装コストがゼロ

#### Disadvantages

- リポジトリ数に比例して確認作業が増える
- 確認漏れが起きやすい
- 定期的に同じ作業を繰り返す必要がある
- Organization 全体の一覧が自動では得られない
- 監査履歴が体系的に残らない

#### Result

**Rejected**

今回解消したい問題そのものを人間に継続させる方式であり、スケールしない。

---

### Option B: Dependabot を各リポジトリへ導入する

各リポジトリに `.github/dependabot.yml` を配置し、`package-ecosystem: github-actions` を設定する。

Dependabot は GitHub Actions の version update を検知し、更新 PR を作成できるため、個々のリポジトリの自動更新手段としては有力である。

#### Advantages

- GitHub 公式機能である
- GitHub Actions の更新を検知できる
- 更新 PR の作成まで自動化できる
- 各リポジトリ単体で完結する

#### Disadvantages

- 原則として **各リポジトリに `dependabot.yml` を配置・維持する必要がある**
- 新しいリポジトリを追加するたび、Dependabot 設定の追加を忘れない運用が必要になる
- Organization 全体の監査結果を 1 枚の中央レポートとして把握する用途には弱い
- 「監査」と「自動更新 PR 作成」が同じ仕組みに寄るため、Phase 1 の Read-only 方針より権限・運用範囲が広くなる
- 今回の主目的である「全リポジトリを横断して古い Action を一括把握する」ことに対しては、個別最適になりやすい

#### Result

**Rejected as the primary architecture for Phase 1**

Dependabot 自体を否定するものではない。

将来的には、Yellow-Talisman が Organization 全体を中央監査し、Dependabot が各リポジトリの更新 PR を生成する、という役割分担で併用できる。

しかし Phase 1 の中心方式としては、すべてのリポジトリへ設定ファイルを配布・維持する必要がある点が、今回解消したい管理負荷と合わないため採用しない。

---

### Option C: Renovate を Organization 横断の更新 Bot として利用する

Renovate の repository autodiscovery 等を利用し、複数リポジトリの依存更新を中央管理する。

#### Advantages

- 多数リポジトリの自動更新に強い
- autodiscover により中央管理しやすい
- GitHub Actions 以外の依存関係にも拡張できる
- 高度な更新ポリシーを設定できる

#### Disadvantages

- 今回必要な「まず監査だけ」という用途に対して機能が大きい
- 導入・権限・設定・運用ポリシーが増える
- Phase 1 の目的より先に自動更新基盤の設計が必要になる
- Yellow-Talisman 固有のレポート形式や分類ルールを実装しにくい

#### Result

**Deferred**

Phase 1 では採用しない。

将来、自動更新 PR を多数リポジトリへ展開する段階で再評価する。

---

### Option D: Yellow-Talisman から Organization 全体を中央監査する

専用の GitHub App を `example-org` にインストールし、アクセス可能なリポジトリを列挙する。

各リポジトリの default branch にある `.github/workflows/*.yml` / `*.yaml` を Read-only で取得し、`uses:` に記述された外部 GitHub Actions を抽出する。

その後、上流 Action repository の Release / Tag を GitHub API から取得し、利用中 ref と比較する。

結果は Yellow-Talisman 自身の以下へ集約する。

```text
reports/github-actions.md
reports/github-actions.json
```

#### Advantages

- 新しいリポジトリが増えても、GitHub App が All repositories を対象としていれば原則追加設定が不要
- Organization 全体を一か所で可視化できる
- 監査対象リポジトリに Write 権限を与える必要がない
- GitHub の実データを基に独自の判定ルールを実装できる
- `MAJOR_OUTDATED`、`FLOATING_BRANCH`、`SHA_PINNED`、`UNRESOLVABLE` など、更新 PR 生成とは別の監査観点を持てる
- Git 管理されたレポートにより、状態変化の履歴を後から追跡できる
- 将来自動更新機構を別コンポーネントとして追加できる

#### Disadvantages

- 監査ロジックを自作・保守する必要がある
- GitHub API rate limit や Release / Tag の例外ケースを扱う必要がある
- SemVer ではない Action など、完全自動判定できないケースがある
- Dependabot のような更新 PR 自動作成機能は Phase 1 には含まれない

#### Result

**Accepted**

---

## 4. Decision

Phase 1 では、**Yellow-Talisman を Organization 横断の中央監査リポジトリとして実装する**。

GitHub App を利用して `example-org` 内の対象リポジトリを Read-only で列挙・走査し、Workflow 内の GitHub Actions 参照を抽出する。

上流 Action の Release / Tag 情報を GitHub API から取得し、利用中の ref と比較して version status を分類する。

監査結果は Yellow-Talisman 自身の `reports/` に Markdown / JSON として保存する。

Phase 1 では対象リポジトリの自動修正、自動 PR、自動 merge は行わない。

---

## 5. Authentication and Permission Decision

対象リポジトリの読み取りと、Yellow-Talisman 自身への report 書き込みは認証を分離する。

```text
GitHub App installation token
  -> Organization 内の対象 repositories
  -> Contents: Read-only

GITHUB_TOKEN
  -> Yellow-Talisman 自身
  -> reports/ の commit に使用
```

この分離により、監査ロジックの不具合が対象リポジトリを書き換えるリスクを抑える。

---

## 6. Version Resolution Decision

「最新バージョン」はコード内に固定した知識や LLM の記憶から判断しない。

GitHub 上の以下を実行時に参照する。

1. Stable Release
2. Release で適切な SemVer が取得できない場合は Tags

また、単純な文字列比較は行わない。

例:

```text
current: actions/checkout@v7
latest stable: v7.0.1
```

この場合、`@v7` は同一 major 系列へ追随する major tag として扱い、`PATCH_OUTDATED` とは判定しない。

一方で:

```text
current: actions/checkout@v3
latest stable: v7.0.1
```

は `MAJOR_OUTDATED` と判定する。

この方針は、Action のバージョン有無について自動レビューが古い知識に基づく誤判定を行う可能性が実際に確認されたことからも重要である。

---

## 7. Reporting Decision

監査結果は Yellow-Talisman 自身に保存する。

```text
Yellow-Talisman/
└── reports/
    ├── github-actions.md
    └── github-actions.json
```

Markdown は人間向け、JSON は将来の自動処理向けとする。

Git 管理する report は deterministic に生成し、実行時刻だけの変化では commit を作らない。

実質的な監査結果が変わった場合のみ report commit を作成する。

これにより Git 履歴自体を監査台帳として利用できる。

### 7.1 Report history retention

`reports/github-actions.md` と `reports/github-actions.json` は、その時点の最新監査結果を表す固定ファイルとして扱う。

実行日時をファイル名へ含めた snapshot ファイルを run ごとに追加保存する方式は採用しない。監査結果が変化した場合のみ同じ固定ファイルを更新して commit し、過去の監査結果を確認したい場合は Git の file history / commit history を参照する。

この方式を採用する理由は、同じ情報を「日時入りファイルの蓄積」と「Git 履歴」の二重で保持する必要がなく、repository 内の report 一覧を常に最新状態だけに保てるためである。また、結果が変わらない run では commit 自体を作らないため、監査実行回数ではなく実質的な状態変化だけが履歴として残る。

将来、時系列集計・統計分析・外部システムへの長期 snapshot 提供など、Git 履歴だけでは扱いにくい要件が発生した場合は、その時点で別の履歴保存方式を検討する。

---

## 8. Execution Decision

監査は以下の 2 経路で同一ロジックを実行する。

- `workflow_dispatch`: 必要時の手動監査
- `schedule`: 定期監査

Phase 1 の初期運用は **weekly + manual** とする。

GitHub Actions の Action 更新は秒単位・分単位で追跡する必要がないため、週次監査を基本とする。

---

## 9. Consequences

### Positive Consequences

- 人間が全リポジトリを定期巡回する必要がなくなる
- 新規リポジトリ追加時の監査設定作業を大幅に減らせる
- Organization 全体の GitHub Actions 状態を中央で確認できる
- 対象リポジトリを Read-only に保てる
- 問題発生の時系列を Git 履歴から追跡できる
- 将来の自動 PR / Dependabot / Renovate 連携の前段となる共通監査データを作れる

### Negative Consequences

- GitHub API client、parser、version resolver、report generator を自前で保守する必要がある
- Action repository ごとの Release / Tag 運用差異を吸収する必要がある
- arbitrary tag や SHA pin など、Phase 1 では完全な鮮度判定ができないケースが残る
- Yellow-Talisman 自身が監査基盤となるため、このリポジトリの保守責任が生じる

---

## 10. Why Dependabot Is Not the Primary Solution

Dependabot は GitHub Actions 更新の自動化手段として有用であり、将来も利用候補から外さない。

ただし今回の問題は「個々のリポジトリで更新 PR を作ること」より先に、**Organization 全体で、どのリポジトリが古い Action を使っているかを継続的に把握すること**である。

各リポジトリに Dependabot 設定を置く方式では、監査対象が増えるたびに設定配布・維持の問題が再び発生する。

したがって:

```text
Yellow-Talisman
  = Organization 全体の中央監査・可視化

Dependabot / Renovate
  = 将来の更新 PR 生成・修復自動化
```

という責務分離を採用する。

---

## 11. Future Evolution

Phase 1 完成後、必要に応じて次を検討する。

### Phase 2

- 新規 `MAJOR_OUTDATED` 発生時の Issue 作成
- Discord / Slack 等への通知
- 前回 report との差分通知

### Phase 3

- 更新 PR の自動生成
- Write 権限を持つ updater と Read-only auditor の分離

### Phase 4

- Dependabot の設定配布
- Renovate autodiscover の導入比較

### Phase 5

- patch / minor の policy-based auto merge
- SHA pin の release 追跡

---

## 12. Revisit Conditions

以下の条件が発生した場合、この ADR を再評価する。

- GitHub が Organization レベルで GitHub Actions の更新状況を一括監査できる公式機能を提供した
- Dependabot が Organization 全体を設定ファイル不要で自動発見・中央レポートできるようになった
- Yellow-Talisman の保守コストが既製ツール導入コストを上回った
- 監査対象が GitHub Actions 以外の依存関係へ大幅に拡大した
- Renovate 等へ監査機能を統合する合理性が高まった

---

## 13. Related Documents

- [`01_project_proposal.md`](01_project_proposal.md)
- [`02_system_design.md`](02_system_design.md)
- [`03_wbs.md`](03_wbs.md)

---

## 14. Summary

Yellow-Talisman は、各リポジトリへ個別設定を配布する方式ではなく、**中央から Organization 全体を Read-only で監査する**。

Dependabot は有用だが、Phase 1 の主目的である「設定対象を増やさず、全リポジトリの状態を一か所で把握する」要件には適合しないため、主方式としては採用しない。

監査と修復を分離し、まず Yellow-Talisman で正確な可視化を完成させ、その後 Dependabot / Renovate / 自動 PR 等を必要に応じて追加する。