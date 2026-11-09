# Detailed documentation index

The original project design and engineering records have been preserved for readers of this public-source candidate. Only references exposing private organization/repository identities and direct links into private GitHub development history were anonymized or removed. The technical text was retained.

**Important distinction:** These are **historical development and deployment documents**. They sometimes describe a private deployment with scheduled audits, self-hosted runners, report commits, organization-specific acceptance gates and modules that are intentionally **not present in the public-source distribution**. They are not setup instructions for a new public checkout. Read [the public operations guide](public_operations.md) for the supported procedure and [the architecture overview](architecture.md) for the public package.

## Detailed project design

- [01 — Project Proposal](01_project_proposal.md)
- [02 — System Design](02_system_design.md)
- [03 — Work Breakdown Structure](03_wbs.md)
- [04 — Architecture Decision Records](04_adr.md)
- [05 — Current Specification (private deployment snapshot)](05_current_specification.md)
- [06 — Component Contracts](06_component_contracts.md)

## Original component-level contracts

- [01 — Models](contracts/01_models.md)
- [02 — GitHub API](contracts/02_github_api.md)
- [03 — Collector](contracts/03_collector.md)
- [04 — Parser](contracts/04_parser.md)
- [05 — Scanner](contracts/05_scanner.md)
- [06 — Version Resolver](contracts/06_version_resolver.md)
- [07 — Report](contracts/07_report.md)
- [08 — Audit](contracts/08_audit.md)
- [09 — Audit Workflow](contracts/09_audit_workflow.md)
- [10 — Limited Dry Run](contracts/10_limited_dry_run.md)
- [11 — Organization Dry Run](contracts/11_organization_dry_run.md)

## Operations

- [Original production runbook — English](operations.md)
- [Original production runbook — Japanese](operations_ja.md)
- [Public-source deployment guide](public_operations.md)

**Redaction policy:** Examples mentioning the former private owner use `example-org` or a fictional sample repository. Historic Issue / PR / commit numbers may remain as non-clickable development references; the former private repository URLs are not distributed. This document index does not grant access to the private development history.