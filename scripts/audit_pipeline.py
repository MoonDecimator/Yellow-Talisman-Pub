"""Resolve a completed scan and assemble its report without writing files."""

from __future__ import annotations

from dataclasses import dataclass

from .github_api import GitHubApi
from .models import AuditReport, ScanResult
from .report import build_audit_report
from .version_resolver import ResolverTelemetry, VersionResolver


@dataclass(frozen=True, slots=True)
class AuditPipelineResult:
    """Report and lookup evidence from a single resolution pass."""

    report: AuditReport
    resolver_telemetry: ResolverTelemetry


def resolve_scan_result(
    api: GitHubApi, scan_result: ScanResult
) -> AuditPipelineResult:
    """Resolve usages with a fresh cache and retain both warning sources."""

    resolver = VersionResolver(api)
    resolution_result = resolver.resolve_with_warnings(scan_result.usages)
    normalized_scan = ScanResult(
        usages=scan_result.usages,
        warnings=scan_result.warnings + resolution_result.warnings,
        repositories_scanned=scan_result.repositories_scanned,
        workflows_scanned=scan_result.workflows_scanned,
    )
    report = build_audit_report(normalized_scan, resolution_result.resolutions)
    return AuditPipelineResult(report, resolver.telemetry)
