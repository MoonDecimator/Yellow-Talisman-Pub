# Yellow-Talisman

GitHub Actions version auditor for GitHub organizations. It scans the repositories accessible to a read-only GitHub App, reads `.github/workflows/*.yml` / `*.yaml`, extracts `uses:` references, compares them with upstream Release/Tag information, and writes Markdown and JSON reports.

**Public distribution safety:** This repository does not contain production audit reports, private organization inventories, credentials, or a workflow that runs an organization scan automatically. No workflow in the public repository uploads or commits actual organization audit output. **Run scans in a private repository or trusted local machine.**

## Capabilities

- Enumerate accessible repositories through a GitHub App installation token
- Scan workflow files on default branches and classify Action references
- Detect outdated major/minor/patch references, unresolved references, and certain nonexistent future version tags
- Generate `reports/github-actions.md` and `reports/github-actions.json`
- Ignore generated `reports/` files in Git
- Leave inspected target repositories unchanged (read-only access)

The `CURRENT` status means no update was detected under the implemented comparison rules; it is **not** a security, compatibility, or reference-existence guarantee. This tool does not automatically change workflows or open update PRs.

## Requirements

- Python 3 (standard library; no runtime packages to install)
- A GitHub App installed on the target repositories, with **Contents: Read-only** and Metadata access
- An ephemeral installation token available locally as `WATCHTOWER_TOKEN`

## Running privately

1. Clone this repository into a **private** environment.
2. Obtain a short-lived GitHub App installation token. Do not place it in source files, CLI arguments, commit history, or shell history.
3. Export `WATCHTOWER_TOKEN` using a secret-aware mechanism in your environment.
4. Run:

```bash
python3 -m scripts.audit --help
python3 -m scripts.audit
```

Reports are written into the ignored `reports/` directory. Treat reports as potentially confidential: they contain repository names, workflow file paths, Action versions, and errors. The CLI also supports `--include`, `--exclude`, `--include-archived`, `--include-forks`, and `--api-url`.

An **inactive example** of a private manual audit workflow is in [examples/private-audit.yml](examples/private-audit.yml). Put it in a *private* repository's `.github/workflows/` only after reviewing permissions and runner requirements; it is intentionally not active here.

## Verification

```bash
python3 -m unittest discover -s tests -v
python3 -m scripts.scanner --help
```

The public CI runs unit tests only. It requires no secrets or access to your GitHub organization.

The private development repository's organization-specific integration and acceptance tests are intentionally excluded. Those tests depend on a particular private inventory, GitHub App installation and runner environment; they are **not expected to run in this public source distribution**. All included public unit tests are expected to pass.

## Project structure

- `scripts/`: collection, parsing, classification, reporting, orchestration, API client
- `tests/`: unit tests and synthetic fixtures
- [`docs/README.md`](docs/README.md): detailed design document index and historical context
- [`docs/architecture.md`](docs/architecture.md): current public-source architecture and limitations
- [`docs/public_operations.md`](docs/public_operations.md): current private-deployment instructions for the public source
- [`docs/01_project_proposal.md`](docs/01_project_proposal.md) through [`docs/06_component_contracts.md`](docs/06_component_contracts.md): restored, minimally sanitized historical design/specification documents
- [`docs/contracts/`](docs/contracts/): restored original component contracts
- [`docs/operations.md`](docs/operations.md) and [`docs/operations_ja.md`](docs/operations_ja.md): restored historical production runbooks (not active public workflows)
- `examples/`: opt-in private deployment example
- `reports/`: generated locally; intentionally not version controlled

Organization-specific acceptance gates, actual repository inventories, private links and commit history, and automatically scheduled report commits are excluded from the public distribution. The original detailed design records are preserved with identifying references anonymized; some historical links to implementation files refer to private-only modules not shipped in this source.

## License

A public distribution license has not yet been chosen. Until a license is added, public visibility alone does not grant permission to reuse, modify, or redistribute the code.
