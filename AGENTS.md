# Contributor and agent guidelines

This public source tree is an organization-agnostic GitHub Actions version auditor.

- Preserve read-only access to scanned repositories.
- Never add real organization inventories, private workflow reports, GitHub tokens, deployment credentials, or personal data.
- Never add automatic organization scans, report artifact uploads, or report commits to the public repository's active workflows.
- Keep generated `reports/` untracked. Real scan results belong in private infrastructure.
- Keep the Python implementation standard-library first; retain deterministic report ordering.
- Use synthetic names and data in unit tests and examples.
- Run `python3 -m unittest discover -s tests -v` before proposing changes.
- Keep changes reviewable using branches and pull requests; do not commit directly to the default branch.
- Keep the README and architecture/operations docs consistent with any feature changes.
