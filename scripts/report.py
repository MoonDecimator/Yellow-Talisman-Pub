"""Build and render deterministic GitHub Actions audit reports."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from .models import (
    AuditError,
    AuditFinding,
    AuditReport,
    AuditSeverity,
    AuditSummary,
    ScanResult,
    VersionResolution,
    VersionStatus,
)


SCHEMA_VERSION = 1
DEFAULT_MARKDOWN_PATH = Path("reports/github-actions.md")
DEFAULT_JSON_PATH = Path("reports/github-actions.json")

SEVERITY_BY_STATUS = {
    VersionStatus.INVALID_REF: AuditSeverity.HIGH,
    VersionStatus.MAJOR_OUTDATED: AuditSeverity.HIGH,
    VersionStatus.UNRESOLVABLE: AuditSeverity.HIGH,
    VersionStatus.UNKNOWN_REF: AuditSeverity.MEDIUM,
    VersionStatus.MINOR_OUTDATED: AuditSeverity.MEDIUM,
    VersionStatus.FLOATING_BRANCH: AuditSeverity.MEDIUM,
    VersionStatus.PATCH_OUTDATED: AuditSeverity.LOW,
    VersionStatus.SHA_PINNED: AuditSeverity.INFO,
    VersionStatus.CURRENT: AuditSeverity.INFO,
}
SEVERITY_ORDER = (
    AuditSeverity.HIGH,
    AuditSeverity.MEDIUM,
    AuditSeverity.LOW,
    AuditSeverity.INFO,
)
STATUS_ORDER = (
    VersionStatus.INVALID_REF,
    VersionStatus.MAJOR_OUTDATED,
    VersionStatus.UNRESOLVABLE,
    VersionStatus.UNKNOWN_REF,
    VersionStatus.MINOR_OUTDATED,
    VersionStatus.PATCH_OUTDATED,
    VersionStatus.FLOATING_BRANCH,
    VersionStatus.SHA_PINNED,
    VersionStatus.CURRENT,
)
STATUS_RANK = {status: rank for rank, status in enumerate(STATUS_ORDER)}


def build_audit_report(
    scan_result: ScanResult,
    resolutions: Iterable[VersionResolution],
) -> AuditReport:
    """Normalize scanner and resolver output into one renderer input."""

    resolution_list = tuple(resolutions)
    if Counter(item.usage for item in resolution_list) != Counter(scan_result.usages):
        raise ValueError("Resolutions must correspond exactly to scanned usages.")

    findings = tuple(
        sorted(
            (_finding_from_resolution(item) for item in resolution_list),
            key=_finding_sort_key,
        )
    )
    errors = tuple(
        sorted(
            (
                AuditError(
                    warning.source_repository,
                    warning.workflow_path,
                    warning.reason,
                )
                for warning in scan_result.warnings
            ),
            key=_error_sort_key,
        )
    )
    severity_counts = Counter(finding.severity for finding in findings)
    status_counts = Counter(finding.status for finding in findings)
    summary = AuditSummary(
        repositories_scanned=scan_result.repositories_scanned,
        workflow_files_scanned=scan_result.workflows_scanned,
        action_usages=len(scan_result.usages),
        unique_actions=len(
            {usage.action_repository.casefold() for usage in scan_result.usages}
        ),
        findings_by_severity=tuple(
            (severity.value, severity_counts[severity])
            for severity in SEVERITY_ORDER
        ),
        findings_by_status=tuple(
            (status.value, status_counts[status]) for status in STATUS_ORDER
        ),
        errors=len(errors),
    )
    return AuditReport(summary, findings, errors)


def render_markdown(report: AuditReport) -> str:
    """Render a human-readable report from a normalized audit report."""

    summary = report.summary
    lines = [
        "# GitHub Actions Version Audit",
        "",
        "## Summary",
        "",
        f"- Repositories scanned: {summary.repositories_scanned}",
        f"- Workflow files scanned: {summary.workflow_files_scanned}",
        f"- Action usages: {summary.action_usages}",
        f"- Unique actions: {summary.unique_actions}",
        f"- Errors: {summary.errors}",
        "",
        "### Findings by severity",
        "",
        "| Severity | Count |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {severity.upper()} | {count} |"
        for severity, count in summary.findings_by_severity
    )
    lines.extend(
        [
            "",
            "### Findings by status",
            "",
            "| Status | Count |",
            "|---|---:|",
        ]
    )
    lines.extend(
        f"| `{status}` | {count} |"
        for status, count in summary.findings_by_status
    )

    sections = (
        (
            "## ⛔ Invalid references",
            (VersionStatus.INVALID_REF,),
        ),
        (
            "## 🔴 Major updates required",
            (VersionStatus.MAJOR_OUTDATED,),
        ),
        (
            "## ❌ Unresolvable and unknown references",
            (VersionStatus.UNRESOLVABLE, VersionStatus.UNKNOWN_REF),
        ),
        (
            "## 🟠 Updates available",
            (VersionStatus.MINOR_OUTDATED, VersionStatus.PATCH_OUTDATED),
        ),
        (
            "## ⚠️ Policy warnings",
            (VersionStatus.FLOATING_BRANCH, VersionStatus.SHA_PINNED),
        ),
        ("## 🟢 Current references", (VersionStatus.CURRENT,)),
    )
    for heading, statuses in sections:
        selected = tuple(
            finding for finding in report.findings if finding.status in statuses
        )
        lines.extend(["", heading, ""])
        lines.extend(_finding_table(selected))

    lines.extend(["", "## Errors", ""])
    lines.extend(_error_table(report.errors))
    return "\n".join(lines) + "\n"


def render_json(report: AuditReport) -> str:
    """Render a machine-readable report from the same normalized model."""

    document = {
        "schema_version": SCHEMA_VERSION,
        "summary": report.summary.to_dict(),
        "findings": [finding.to_dict() for finding in report.findings],
        "errors": [error.to_dict() for error in report.errors],
    }
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def write_reports(
    report: AuditReport,
    *,
    markdown_path: Path = DEFAULT_MARKDOWN_PATH,
    json_path: Path = DEFAULT_JSON_PATH,
) -> None:
    """Write both deterministic report formats without Git operations."""

    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(render_json(report), encoding="utf-8")


def _finding_from_resolution(resolution: VersionResolution) -> AuditFinding:
    usage = resolution.usage
    return AuditFinding(
        source_repository=usage.source_repository,
        workflow_path=usage.workflow_path,
        line_number=usage.line_number,
        action_repository=usage.action_repository,
        subpath=usage.subpath,
        current_ref=usage.ref,
        ref_kind=resolution.ref_kind,
        latest_stable=resolution.catalog.latest_stable,
        status=resolution.status,
        severity=SEVERITY_BY_STATUS[resolution.status],
    )


def _finding_sort_key(finding: AuditFinding) -> tuple[object, ...]:
    return (
        STATUS_RANK[finding.status],
        finding.source_repository.casefold(),
        finding.source_repository,
        finding.workflow_path.casefold(),
        finding.workflow_path,
        finding.line_number,
        finding.action_repository.casefold(),
        finding.action_repository,
        finding.current_ref,
    )


def _error_sort_key(error: AuditError) -> tuple[str, ...]:
    workflow = error.workflow_path or ""
    return (
        error.source_repository.casefold(),
        error.source_repository,
        workflow.casefold(),
        workflow,
        error.reason.casefold(),
        error.reason,
    )


def _finding_table(findings: tuple[AuditFinding, ...]) -> list[str]:
    if not findings:
        return ["_No findings._"]
    rows = [
        "| Repository | Workflow | Line | Action | Current | Latest | Status |",
        "|---|---|---:|---|---|---|---|",
    ]
    for finding in findings:
        action = finding.action_repository
        if finding.subpath is not None:
            action = f"{action}/{finding.subpath}"
        rows.append(
            "| "
            + " | ".join(
                (
                    _markdown_cell(finding.source_repository),
                    _markdown_cell(finding.workflow_path),
                    str(finding.line_number),
                    _markdown_cell(action),
                    _markdown_cell(finding.current_ref),
                    _markdown_cell(finding.latest_stable or "—"),
                    f"`{finding.status.value}`",
                )
            )
            + " |"
        )
    return rows


def _error_table(errors: tuple[AuditError, ...]) -> list[str]:
    if not errors:
        return ["_No errors._"]
    rows = [
        "| Repository | Workflow | Reason |",
        "|---|---|---|",
    ]
    for error in errors:
        rows.append(
            "| "
            + " | ".join(
                (
                    _markdown_cell(error.source_repository),
                    _markdown_cell(error.workflow_path or "—"),
                    _markdown_cell(error.reason),
                )
            )
            + " |"
        )
    return rows


def _markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")
