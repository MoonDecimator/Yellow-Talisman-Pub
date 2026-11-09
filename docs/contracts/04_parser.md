# C04. Workflow Parser

現行境界の観測であり、要求への適合認定ではありません。[資料索引・更新方針](../06_component_contracts.md)を参照してください。

## 責務と前提

[parser.py](../../scripts/parser.py)の`parse_workflow(workflow: WorkflowFile) -> tuple[ActionUsage, ...]`は、渡された本文から外部`uses:`参照を抽出します。[C01](01_models.md)のWorkflowFileにsource repository・path・文字列の本文が設定されていることを前提とします。

API照会、ref実在確認、YAML全体の構文・意味検証、呼び出し先本文の再帰取得は担当しません。Workflow本文を実行しません。

## 正常出力

- 返却順は本文の出現順。`line_number`は`splitlines()`による1始まりの元行番号。
- `source_repository` / `workflow_path`は入力から保持。`raw`は外側の引用符・コメント等を処理した参照値で、元の行全文ではない。
- `owner/repo[/subpath]@ref`を最後の`@`で分割する。owner / repoに許す文字とsubpathの拒否条件は正規表現・実装に従う。
- subpathがなければ`None`。`.github/workflows/`で始まり`.yml` / `.yaml`で終わるsubpathは`kind="reusable_workflow"`、それ以外は`github_action`。
- 同じActionの別行参照は別usageとして保持し、dedupしない。

## 除外・空結果・限界

- `./`、`../`、大文字小文字を問わない`docker://`参照は除外する。
- 行ベースで認識したliteral / folded block scalarの本文内にある`uses:`は除外する。
- 空値、閉じない引用符、引用符後の不正な残余、ref内の空白、必要部分のない参照などはusageにせず、warningも返さない。
- 認識できる参照がなければ空tuple。これは「YAMLが正しい」「外部参照が本当に存在しない」という証明ではない。
- YAMLのanchor / alias展開、flow形式全般、文字列escape全般を実装したParserではない。任意のYAMLへ対応すると保証しない。

型に沿った入力の解析ではI/Oなし。入力値の型検証や、想定外のPython例外をCollectionWarningへ変換する責任は持ちません。

## 境界例

本文の2行目が`- uses: owner/repo/tool@v1`なら、source位置を保ち、`action_repository="owner/repo"`、`subpath="tool"`、`ref="v1"`のusageになります。バージョンの判定は[C06](06_version_resolver.md)へ渡します。

## レビュー資料と確認点

[test_parser.py](../../tests/test_parser.py)と[workflow_mixed.yml](../../tests/fixtures/workflow_mixed.yml)を渡します。`test_ignores_uses_inside_literal_and_folded_block_scalars`、`test_rejects_malformed_references`、`test_preserves_raw_reference_and_source_fields`が代表例です。抽出できる形式と、Resolverが比較できる形式を区別します。[S-02](../05_current_specification.md#s-02短縮semverの扱い)・[S-03](../05_current_specification.md#s-03参照の実在確認とcurrentの意味)の解決をParserの成功から推論しません。
