# Yellow-Talisman Operations Runbook

> **Historical private-deployment runbook.** This document describes the original internal operating environment, not the active workflows shipped in the public source. See [Public deployment guide](public_operations.md) for supported setup. No private report data or credential values are included.


## 1. Purpose

This runbook describes the routine operation and recovery procedures for the Phase 1 production audit.

Yellow-Talisman scans GitHub Actions references across repositories accessible to its GitHub App and maintains the latest audit snapshot in:

- `reports/github-actions.md` — human-readable report
- `reports/github-actions.json` — machine-readable report

Historical snapshots are not created as timestamped files. When report contents change, the fixed report files are committed; use Git history to inspect previous states.

## 2. Normal operation

The production workflow is `.github/workflows/audit.yml`.

It supports:

- scheduled execution by GitHub Actions cron (Sunday 04:17, `Asia/Tokyo`)
- manual execution with `workflow_dispatch`

A normal run performs the audit, uploads the generated reports as an artifact, then commits the two report files only when their contents have materially changed. A no-change run succeeds without creating a report commit.

### Self-hosted runner prerequisites

All workflows use `runs-on: [self-hosted, linux, x64]`. Ensure that the repository or Organization has at least one online Linux x64 self-hosted runner carrying the `self-hosted`, `linux`, and `x64` labels. If no matching runner is online, both scheduled and manually dispatched runs remain queued.

The runner must provide at least `bash`, `git`, `python3`, `gh`, and `jq`, plus common GNU/Linux commands such as `base64`, `grep`, `sed`, `tr`, and `wc`. It must also be able to reach GitHub, the GitHub API, and GitHub Actions download endpoints over HTTPS.

## 3. Manual audit

To run an audit on demand:

1. Open the Yellow-Talisman repository in GitHub.
2. Open **Actions**.
3. Select **GitHub Actions audit**.
4. Select **Run workflow** and dispatch the workflow from the production branch, `main`.
5. Confirm that both `audit` and `commit-report` complete successfully.

Manual dispatch is safe for routine use. Avoid intentionally starting overlapping runs; the workflow has concurrency protection, but duplicate executions provide no operational benefit.

## 4. Confirming a successful run

For each production run, confirm:

- the workflow conclusion is `Success`
- `audit` completed successfully
- `commit-report` completed successfully
- the audit summary reports no unexpected partial errors
- if the generated report contents changed, `reports/github-actions.md` and `reports/github-actions.json` were updated
- if the generated report contents did not change, no report-only commit was created

For the scheduled production check, also confirm that the run event is `schedule`, not `workflow_dispatch`.

## 5. Reading the report

Start with `reports/github-actions.md`.

The current detail sections show invalid future version references (`INVALID_REF`, high severity) first, followed by `MAJOR_OUTDATED`, unresolved references (`UNRESOLVABLE` / `UNKNOWN_REF`), minor / patch updates, policy warnings, and `CURRENT`, then Errors. `INVALID_REF` means a numeric version ref newer than the latest stable version was found neither as an exact upstream tag nor as a branch; it does not imply that every other ref was checked for existence. The full status order and severity mapping are in the [current-specification index](05_current_specification.md#4-reportの現行表示).

`UNKNOWN_REF` had no position in the original proposal's priority list; the current renderer places it in the unresolved-reference section. Do not infer ref existence, compatibility, or safety from `CURRENT`. The number of `UNRESOLVABLE` findings and the Errors count are different metrics; inspect both.

The report is an audit result, not an instruction to update automatically. Phase 1 does not modify target repositories, open update PRs, or merge dependency changes.

Use `reports/github-actions.json` when structured output is needed for scripts or later integrations.

## 6. Report history

The report filenames are intentionally stable. Do not create files such as `github-actions-YYYY-MM-DD.md` for routine runs.

To inspect an older audit state, open the Git history for the relevant report file and view the desired commit. This keeps the repository focused on the current state while preserving changed historical states through Git.

## 7. Failure visibility

A production failure is visible in GitHub Actions as a failed workflow/job/step. Begin diagnosis from the failed step rather than rerunning repeatedly.

Useful evidence includes:

- workflow event (`schedule` or `workflow_dispatch`)
- failed job and step
- audit summary
- API error/status information
- whether an artifact was produced
- whether the failure occurred before or during `commit-report`

Never copy secrets, tokens, or private-key material into an Issue, log excerpt, or troubleshooting note.

## 8. Troubleshooting

### Authentication failure

Check that the repository configuration still contains the expected GitHub App configuration and that the App remains installed for the intended repositories. Confirm that the private-key Secret exists, but never print its value.

### Repository is missing from the audit

Check the GitHub App installation scope first. Yellow-Talisman can only enumerate repositories available to the App installation. In the current production workflow, the default `RepositoryFilter` also excludes archived repositories and forks. The audit CLI exposes `--include` / `--exclude`, but the production workflow passes no filter arguments. Loading `config/watchtower.yml` is not implemented. See the [current-specification index](05_current_specification.md#3-設定と実行経路) for configuration entry points and the difference from the original requirement.

### Workflow files are missing

Confirm that the repository's default branch contains `.github/workflows/*.yml` or `.github/workflows/*.yaml` and that the GitHub App can read repository contents.

### Version resolution fails

Inspect the finding and API error information. Upstream repositories may have unusual tags, unavailable releases, deleted refs, or temporary API failures. Do not treat an unresolved reference as automatically safe or outdated.

### Report was not committed

This is expected when the generated report has no material difference from the committed report. The production workflow intentionally avoids no-op commits.

If the report should have changed, inspect the generated artifact and the `commit-report` job to determine whether the difference was generated and detected.

### Commit step fails

Check the Yellow-Talisman repository's workflow permissions and branch protection. The GitHub App credential used for target repositories is read-only; report commits use Yellow-Talisman's own `GITHUB_TOKEN` path and must not be replaced with target-repository write access.

### Scheduled run did not appear

Confirm that the production workflow exists on the default branch and still contains the `schedule` trigger. Also inspect GitHub Actions status/history for repository-level workflow disablement or scheduling issues. A manual dispatch can be used to distinguish a scheduling problem from an audit implementation problem.

## 9. Recovery procedure

When production auditing is unhealthy:

1. Identify the most recent successful production run.
2. Identify whether the failure is scheduling, authentication, collection, version resolution, report generation, or report commit related.
3. Correct the smallest responsible configuration or code path.
4. Run the production workflow manually with `workflow_dispatch`.
5. Confirm both jobs succeed and inspect the resulting report/artifact.
6. Leave the scheduled trigger enabled and confirm the next scheduled run normally.

Do not broaden GitHub App permissions as a generic troubleshooting step.

## 10. Secret rotation

Rotate the GitHub App private key when it may have been exposed, when it is revoked, or as part of planned credential maintenance.

1. In the GitHub App settings, generate a new private key while the existing key is still available when possible.
2. Replace the Yellow-Talisman Actions Secret `WATCHTOWER_APP_PRIVATE_KEY` with the complete new private key. Do not paste the key into source files, Issues, PR comments, logs, or command-line arguments.
3. Run **GitHub Actions audit** manually with `workflow_dispatch` and confirm that both `audit` and `commit-report` succeed.
4. Confirm that repository enumeration and report generation work normally with the new key.
5. Only after successful verification, delete/revoke the old GitHub App private key if it remains active.
6. If verification fails, restore service with a known-valid key where possible, diagnose the failure without exposing key material, and repeat the rotation.

When rotating because of suspected compromise, treat the old key as untrusted and revoke it as soon as the replacement has been installed and verified. Do not retain old private-key material in project documentation or troubleshooting records.

## 11. Security boundaries

The Phase 1 security boundary is deliberate:

- the GitHub App reads target repositories
- target repositories are not modified by Yellow-Talisman
- the App should not be granted Contents Write for Phase 1
- report commits are limited to the Yellow-Talisman repository
- credentials must not be placed in source files, command-line arguments, generated reports, or logs

If a future phase requires write access to target repositories, treat that as a separate design and security decision rather than silently expanding the Phase 1 App permissions.

## 12. Related documentation

- `README.md` — purpose, setup, report overview, and project entry point
- `docs/01_project_proposal.md` — project background and scope
- `docs/02_system_design.md` — detailed architecture and security design
- `docs/03_wbs.md` — implementation and acceptance work breakdown
- `docs/04_adr.md` — architecture decisions and rationale
- [Current specification](05_current_specification.md) — Current behavior, implementation/test references, and unresolved specification differences.
