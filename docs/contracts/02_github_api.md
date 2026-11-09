# C02. GitHub API

現行境界の観測であり、要求への適合認定ではありません。[資料索引・更新方針](../06_component_contracts.md)を参照してください。

## 責務と呼び出し側の前提

[github_api.py](../../scripts/github_api.py)は認証付きGET、pagination、retry、API統計を担当します。404を空結果・finding・warningのどれにするかは呼び出し側が決めます。

`GitHubApi(token, *, api_url, transport, max_attempts, backoff_base_seconds, sleep, clock)`のtokenは空でなく、試行回数は1以上、backoffは0以上が必要です。これらの違反は`ValueError`です。token発行・失効更新は担当しません。テストではtransport / sleep / clockを差し替えられます。

呼び出し側は信頼するAPI endpointを渡します。実装は絶対HTTP(S) URLとpaginationのnext URLも使用し、同一originへの制限を検証しません。型注釈どおりの応答・transportを前提とし、任意の外部応答に対するschema検証器ではありません。

## 入出力

| 操作 | 正常時 | 注意点 |
|---|---|---|
| `get_json(path, *, params=None)` | UTF-8 JSONをdecodeした値 | 戻り値は`Any`。辞書や必須keyの保証はない |
| `get_text(path, *, params=None, accept=...)` | UTF-8文字列 | 既定のAcceptはraw content用 |
| `get_paginated(path, *, item_key=None, params=None)` | itemを順にyieldするiterator | 消費時にI/O。既定`per_page=100`、`Link rel=next`を辿る |
| `telemetry` | `ApiTelemetry`のsnapshot | インスタンス内の累積値 |

paginationは配列、または`item_key`の指す配列を必要とします。非配列は`TypeError`、不足keyは`KeyError`となり得ます。空配列とnextなしは正常終了です。後続ページで失敗すると、それまでにyieldしたitemは取り消されません。

## 例外・retry・統計

- HTTP 404は`GitHubNotFoundError`、その他のHTTP失敗は`GitHubApiError`。`status`、`url`、`rate_limited`を持つ。404はretryしない。
- 429、5xx、rate-limitedと判定した403、`TimeoutError` / `URLError`を既定で初回込み最大3試行。通信失敗の最終エラーは`status=None`。
- 待機は解釈可能な`Retry-After`、reset時刻、指数backoffの順。要求時間全体の上限は設けていない。
- `is_fatal_api_error()`は404以外の4xxをtrueにする。[S-05](../05_current_specification.md#s-05全体停止するapiエラーの範囲)の判断は未解決。
- UTF-8 / JSON decode失敗、想定外の応答形状などは、すべてが`GitHubApiError`に統一されるわけではない。
- `requests`はtransport試行数、`retries`は再試行待機の回数。remainingは観測した最小値を保持し、同値以下の観測に対応するresetへ更新する。最新応答の残量とは限らず、未観測は`None`。

## 副作用と対象外

ネットワークGET、待機、インスタンス内統計の更新があります。repositoryへ書き込みません。API層が低remainingのwarningを生成する機能はなく、[S-04](../05_current_specification.md#s-04rate-limit閾値warning)として引き継ぎます。

## レビュー資料と確認点

[test_github_api.py](../../tests/test_github_api.py)の`test_pagination_follows_next_link`、`test_429_prefers_retry_after_over_rate_limit_reset`、`test_exhausted_retry_raises_last_api_error`、`test_fatal_policy_distinguishes_scoped_failures`が代表例です。これらを時間上限・全応答形式の保証へ広げません。404の意味付けは[C03](03_collector.md)と[C06](06_version_resolver.md)を併読します。
