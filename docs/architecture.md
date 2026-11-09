# Architecture

The audit pipeline is designed to **read** workflow files from GitHub App-accessible repositories and **write** reports only to a local output directory.

```text
GitHub App token (read-only)
    -> RepositoryCollector
    -> Workflow Scanner / uses parser
    -> VersionResolver (Release/Tag metadata)
    -> Report renderer (Markdown + JSON)
```

The modules in `scripts/` separate GitHub API transport, repository collection, workflow extraction, action reference classification, and report formatting. `python3 -m scripts.audit` runs the pipeline; `python3 -m scripts.scanner` offers intermediate scan output.

## Status and limits

Reports can include `INVALID_REF`, `MAJOR_OUTDATED`, `MINOR_OUTDATED`, `PATCH_OUTDATED`, `UNRESOLVABLE`, `UNKNOWN_REF`, `FLOATING_BRANCH`, `SHA_PINNED`, and `CURRENT`. Not every ref is verified to exist. Some short version forms and SHA-pinned refs are not fully freshness-checked. Release/Tag availability and GitHub API errors affect results.

This is a **version audit**, not malicious-action detection, dependency vulnerability scanning, or a guarantee that an action is compatible with a workflow.

## Security boundary

- The GitHub App installation token needs only repository **Contents: Read-only** and implicit Metadata access for the target inventory.
- Do not grant write access to audited repositories.
- Run privately. Report files may reveal private repository names, paths, versions, and operational details.
- The public repository's CI does not use the GitHub App, run audits, or publish report artifacts.
- The optional example in `examples/private-audit.yml` is a starting point for a private installation, not an active workflow.

Previous internal acceptance-test gates and fixed inventories were intentionally removed from this public package because they were tailored to one organization's private environment.
