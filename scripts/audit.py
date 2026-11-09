"""Orchestrate scanning, version resolution, and report generation."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from .audit_pipeline import resolve_scan_result
from .collector import RepositoryFilter
from .github_api import DEFAULT_API_URL, ApiTelemetry, GitHubApi, GitHubApiError
from .models import AuditReport
from .report import (
    DEFAULT_JSON_PATH,
    DEFAULT_MARKDOWN_PATH,
    write_reports,
)
from .scanner import scan


def run_audit(
    api: GitHubApi,
    policy: RepositoryFilter,
    *,
    markdown_path: Path = DEFAULT_MARKDOWN_PATH,
    json_path: Path = DEFAULT_JSON_PATH,
) -> AuditReport:
    """Run the complete read-only audit pipeline and write both reports."""

    scan_result = scan(api, policy)
    report = resolve_scan_result(api, scan_result).report
    write_reports(report, markdown_path=markdown_path, json_path=json_path)
    return report


def write_job_summary(
    path: Path,
    report: AuditReport,
    telemetry: ApiTelemetry,
) -> None:
    """Append audit and API telemetry to the GitHub Actions Job Summary."""

    summary = report.summary
    lines = [
        "## GitHub Actions audit",
        "",
        (
            "Requested target token permissions: "
            "`contents=read`, `metadata=read`."
        ),
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Repositories scanned | {summary.repositories_scanned} |",
        f"| Workflow files scanned | {summary.workflow_files_scanned} |",
        f"| Action usages | {summary.action_usages} |",
        f"| Unique actions | {summary.unique_actions} |",
        f"| Partial errors | {summary.errors} |",
        "",
        "### Findings by severity",
        "",
        "| Severity | Count |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {severity} | {count} |"
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
    lines.extend(
        [
            "",
            "### GitHub API telemetry",
            "",
            f"- Requests: {telemetry.requests}",
            f"- Retries: {telemetry.retries}",
            "- Rate limit remaining: "
            f"{_optional_number(telemetry.rate_limit_remaining)}",
            f"- Rate limit reset (epoch): {_optional_number(telemetry.rate_limit_reset)}",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as summary_file:
        summary_file.write("\n".join(lines))


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Run the audit CLI, returning nonzero only for a fatal failure."""

    arguments = _argument_parser().parse_args(argv)
    environment = os.environ if environ is None else environ
    token = environment.get("WATCHTOWER_TOKEN")
    if not token:
        print("fatal: WATCHTOWER_TOKEN is required", file=sys.stderr)
        return 1

    api = GitHubApi(token, api_url=arguments.api_url)
    policy = RepositoryFilter(
        include_archived=arguments.include_archived,
        include_forks=arguments.include_forks,
        included_repositories=frozenset(arguments.include),
        excluded_repositories=frozenset(arguments.exclude),
    )
    try:
        report = run_audit(api, policy)
        summary_path = environment.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            write_job_summary(Path(summary_path), report, api.telemetry)
    except (GitHubApiError, OSError, TypeError, ValueError) as error:
        print(f"fatal: audit failed: {error}", file=sys.stderr)
        return 1

    print(
        "audit complete: "
        f"{report.summary.repositories_scanned} repositories, "
        f"{report.summary.workflow_files_scanned} workflows, "
        f"{report.summary.action_usages} uses, "
        f"{report.summary.errors} partial errors",
        file=sys.stderr,
    )
    return 0


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit GitHub Actions versions and generate reports"
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--include", action="append", default=[], metavar="REPOSITORY")
    parser.add_argument("--exclude", action="append", default=[], metavar="REPOSITORY")
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument("--include-forks", action="store_true")
    return parser


def _optional_number(value: int | None) -> str:
    return "not observed" if value is None else str(value)


if __name__ == "__main__":
    raise SystemExit(main())
