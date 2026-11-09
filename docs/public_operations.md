# Private deployment and operations

## Installation

1. Install the application source in a **private** GitHub repository or on a trusted machine.
2. Create a GitHub App with `Contents: Read-only` access, install it on the repositories you intend to inspect, and generate an installation token when you run the audit.
3. Pass the token as `WATCHTOWER_TOKEN`. Do not store token values in Git, workflow YAML, CLI arguments, or logs.
4. Run `python3 -m scripts.audit` in the repository root.
5. Inspect the generated `reports/github-actions.md` and `reports/github-actions.json` in a secure location.

Use `--include` / `--exclude` to narrow the scan. Archived and fork repositories are excluded by default.

## Scheduling and artifacts

This public source repository deliberately has **no scheduled organization scan** and **no report-commit workflow**. To schedule your own private installation, place an adapted copy of [the manual example](../examples/private-audit.yml) in your private repository and review its token permissions and artifact access. The example does not push reports to Git.

**Do not put actual scan reports in a public repository or publish them through public Actions artifacts.** Add a private destination or an access-controlled storage mechanism if retention is needed.

## Verification

Run `python3 -m unittest discover -s tests -v` after updates. Check GitHub App scope, API rate limits, and whether the intended repositories are installed before treating a zero-result scan as complete. Reported `CURRENT` references are not guaranteed safe or functional.

## Secret rotation

Rotate the GitHub App private key through GitHub's App settings and update the private installation's secret store. Revoke or rotate any token or key accidentally exposed; deleting a secret from the latest commit is insufficient after publication.
