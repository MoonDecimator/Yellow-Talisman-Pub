# C06. Version Resolver

現行境界の観測であり、要求への適合認定ではありません。[資料索引・更新方針](../06_component_contracts.md)を参照してください。

## 責務と依存

[version_resolver.py](../../scripts/version_resolver.py)は[C01 ActionUsage](01_models.md)を上流Release / Tagsと照合し、usageごとのVersionResolutionを返します。severity、Reportの順序、Git操作は担当しません。API取得とretryは[C02](02_github_api.md)へ委譲します。

## 入出力と前提

| 操作 | 正常出力 |
|---|---|
| `parse_semver(value)` | 完全なstable数値形式を`SemanticVersion`へ変換、非対応形式は`None` |
| `classify_static_ref(ref)` | SHA / major / 完全SemVerの分類と値、それ以外は`None` |
| `VersionResolver(api).build_catalog(usages)` | Action repositoryのcasefold単位で1つのcatalog、keyのsort順 |
| `resolve(usages)` | 入力と同じ順序・個数のresolution tuple |
| `resolve_with_warnings(usages)` | 同じ順序・個数のresolutionsとwarningsを持つ`ResolutionResult` |
| `telemetry` | catalog / branchのlookup・cache hitの累積snapshot |

usageにはParser相当のrepositoryとref文字列を渡します。入力モデルの形式検証はしません。空入力では空結果で、上流照会はありません。

## 分類とcatalog

- SemVerは小文字`v`を任意で付けた`major.minor.patch`。先頭ゼロ、prerelease、build metadata、短縮形は受け付けない。40桁の16進SHAはmajor判定より先に分類する。
- draft / prereleaseを除外したReleaseに解釈可能な候補があれば最大の数値候補を採用。候補がない場合にTagsへfallbackする。**Release APIの404はTags fallbackではなく取得不能**になる。
- 上流catalogが取得不能ならref種別より`UNRESOLVABLE`を優先する。上流取得可能でも数値候補なしなら数値refは`UNRESOLVABLE`、SHAは`SHA_PINNED`。
- 静的分類できないrefは、`main` / `master`も含めbranch endpointを照会し、存在すれば`FLOATING_BRANCH`、404なら`UNKNOWN_REF`。
- majorが最新majorより小さければ`MAJOR_OUTDATED`。完全SemVerはmajor / minor / patch差を比較する。最新安定候補を超えるmajor / 完全SemVerでは、同名Git Tagが存在すれば`CURRENT`、Tagがなく同名Branchが存在すればref kindを`BRANCH`として`FLOATING_BRANCH`、両方存在しなければ`INVALID_REF`とする（Issue #40）。
- 最新以下の数値ref・SHAそれ自体の実在、subpathの存在、互換性・安全性は検証しない。reusable workflowも参照先repository単位の比較である。

## 失敗とcache

Release / Tagsの404はcatalogに保持され、findingへ反映されます。この経路だけではwarningを生成しません。branch 404は不在の分類になり、warningにはしません。未来数値refのTag確認は`/git/ref/tags/{ref}`を使用し、prefix一致のレスポンスは有効なTagと認めません。Tag / Branchの両方が404の場合だけ`INVALID_REF`です。404以外のAPIエラーは既存の伝播・部分失敗処理に従い、存在しないと断定しません。

`resolve()`はそれ以外のAPI失敗を伝播します。`resolve_with_warnings()`は回復可能なAPI失敗をAction repository単位で捕捉し、そのActionの**全usage**を`UNRESOLVABLE`へ置き換え、各source repository / workflowにつき1件のwarningを付けます。同じActionの一部のrefを先に分類できていても、グループの失敗時は置き換わります。fatal API失敗や想定外の非API例外は伝播します。

catalogのkeyはAction repositoryのcasefold、branch / tag cacheのkeyはそのcasefoldとrefの組です。cacheはインスタンス内で呼び出しを跨いで保持し、失敗を捕捉して作った404 catalogやbranch / tag不在もcacheします。永続化・期限切れ・並行利用の保証はありません。副作用はAPI GETとcache・統計更新です。

## レビュー資料と未解決事項

[test_version_resolver.py](../../tests/test_version_resolver.py)の`test_tolerant_resolution_keeps_other_actions_after_5xx`、`test_tolerant_resolution_deduplicates_warnings_by_workflow`、`test_reuses_catalog_cache_across_resolve_calls`、`test_main_is_verified_instead_of_assumed_to_be_a_branch`が代表例です。[Resolver Gate](../../.github/workflows/version-resolver-gate-smoke-test.yml)はlive期待値を別に確認します。

[S-02 短縮形](../05_current_specification.md#s-02短縮semverの扱い)、[S-03 実在確認](../05_current_specification.md#s-03参照の実在確認とcurrentの意味)、[S-05 停止範囲](../05_current_specification.md#s-05全体停止するapiエラーの範囲)、[S-08 Errors収録](../05_current_specification.md#s-08errorsへの収録範囲)は未解決です。API取得成功・`CURRENT`・warningなしをこれらの要求の充足とみなしません。
