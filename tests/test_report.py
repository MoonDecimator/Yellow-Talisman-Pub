import json
from pathlib import Path
import tempfile
import unittest

from scripts.models import (
    ActionCatalogEntry,
    ActionUsage,
    AuditSeverity,
    CollectionWarning,
    RefKind,
    ScanResult,
    SemanticVersion,
    VersionResolution,
    VersionStatus,
)
from scripts.report import (
    STATUS_ORDER,
    build_audit_report,
    render_json,
    render_markdown,
    write_reports,
)


FIXTURES = Path(__file__).parent / "fixtures"


def resolution(
    status,
    *,
    repository="org/source",
    workflow=".github/workflows/ci.yml",
    line=1,
    action="actions/checkout",
    ref="v7",
    ref_kind=RefKind.MAJOR_TAG,
    latest="v7.0.1",
    subpath=None,
):
    usage = ActionUsage(
        source_repository=repository,
        workflow_path=workflow,
        line_number=line,
        raw=f"{action}@{ref}",
        action_repository=action,
        subpath=subpath,
        ref=ref,
        kind="github_action",
    )
    version = (
        SemanticVersion(
            *(int(part) for part in latest.removeprefix("v").split("."))
        )
        if latest is not None
        else None
    )
    catalog = ActionCatalogEntry(
        action_repository=action,
        latest_stable=latest,
        latest_version=version,
        source="release" if latest is not None else None,
        repository_available=status is not VersionStatus.UNRESOLVABLE,
    )
    return VersionResolution(usage, ref_kind, status, catalog)


def scan_result(resolutions, *, warnings=(), repositories=2, workflows=3):
    return ScanResult(
        usages=tuple(item.usage for item in resolutions),
        warnings=tuple(warnings),
        repositories_scanned=repositories,
        workflows_scanned=workflows,
    )


class AuditReportModelTests(unittest.TestCase):
    def test_summary_counts_case_insensitive_unique_actions(self):
        resolutions = (
            resolution(
                VersionStatus.CURRENT,
                action="Actions/Checkout",
                repository="org/one",
            ),
            resolution(
                VersionStatus.MAJOR_OUTDATED,
                action="actions/checkout",
                repository="org/two",
                ref="v3",
            ),
            resolution(
                VersionStatus.CURRENT,
                action="owner/other",
                repository="org/three",
            ),
        )

        report = build_audit_report(scan_result(resolutions), resolutions)

        self.assertEqual(3, report.summary.action_usages)
        self.assertEqual(2, report.summary.unique_actions)

    def test_assigns_a_severity_to_every_status(self):
        expected = {
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
        resolutions = tuple(
            resolution(
                status,
                line=index,
                latest=(
                    None
                    if status is VersionStatus.UNRESOLVABLE
                    else "v7.0.1"
                ),
            )
            for index, status in enumerate(expected, start=1)
        )

        report = build_audit_report(scan_result(resolutions), resolutions)

        self.assertEqual(
            expected,
            {finding.status: finding.severity for finding in report.findings},
        )

    def test_sorts_findings_by_status_then_stable_source_fields(self):
        resolutions = tuple(
            resolution(
                status,
                repository="org/Zebra" if index % 2 else "org/alpha",
                workflow="z.yml" if index % 2 else "a.yml",
                line=10 - index,
                latest=None if status is VersionStatus.UNRESOLVABLE else "v7.0.1",
            )
            for index, status in enumerate(reversed(STATUS_ORDER), start=1)
        )

        report = build_audit_report(scan_result(resolutions), resolutions)

        self.assertEqual(list(STATUS_ORDER), [item.status for item in report.findings])

    def test_sorts_errors_by_repository_workflow_and_reason(self):
        warnings = (
            CollectionWarning("org/zebra", "z.yml", "Beta"),
            CollectionWarning("org/alpha", "z.yml", "Zulu"),
            CollectionWarning("org/alpha", None, "Repository error"),
            CollectionWarning("org/alpha", "a.yml", "Zulu"),
            CollectionWarning("org/alpha", "a.yml", "Alpha"),
        )

        report = build_audit_report(scan_result((), warnings=warnings), ())

        self.assertEqual(
            [
                ("org/alpha", None, "Repository error"),
                ("org/alpha", "a.yml", "Alpha"),
                ("org/alpha", "a.yml", "Zulu"),
                ("org/alpha", "z.yml", "Zulu"),
                ("org/zebra", "z.yml", "Beta"),
            ],
            [
                (error.source_repository, error.workflow_path, error.reason)
                for error in report.errors
            ],
        )

    def test_rejects_missing_or_unrelated_resolutions(self):
        item = resolution(VersionStatus.CURRENT)

        with self.assertRaises(ValueError):
            build_audit_report(scan_result((item,)), ())


class ReportRendererTests(unittest.TestCase):
    def setUp(self):
        self.resolutions = (
            resolution(
                VersionStatus.CURRENT,
                repository="org/zeta",
                workflow="current.yml",
                line=12,
            ),
            resolution(
                VersionStatus.MAJOR_OUTDATED,
                repository="org/alpha",
                workflow="update.yml",
                line=4,
                action="owner/action",
                ref="v1",
                latest="v2.0.0",
            ),
            resolution(
                VersionStatus.FLOATING_BRANCH,
                repository="org/alpha",
                workflow="branch.yml",
                line=8,
                action="owner/branch-action",
                ref="develop",
                ref_kind=RefKind.BRANCH,
            ),
        )
        self.warnings = (
            CollectionWarning("org/zeta", "missing.yml", "file disappeared"),
        )
        self.report = build_audit_report(
            scan_result(self.resolutions, warnings=self.warnings),
            self.resolutions,
        )

    def test_markdown_contains_summary_problem_first_and_errors(self):
        rendered = render_markdown(self.report)

        self.assertIn("- Repositories scanned: 2", rendered)
        self.assertIn("- Workflow files scanned: 3", rendered)
        self.assertIn("- Action usages: 3", rendered)
        self.assertIn("- Unique actions: 3", rendered)
        self.assertIn("file disappeared", rendered)
        self.assertLess(
            rendered.index("## 🔴 Major updates required"),
            rendered.index("## 🟢 Current references"),
        )

    def test_invalid_future_ref_is_high_severity_in_both_reports(self):
        item = resolution(
            VersionStatus.INVALID_REF,
            repository="example-org/sample-repo",
            workflow=".github/workflows/claude.yml",
            line=24,
            ref="v8",
            latest="v7.0.1",
        )
        report = build_audit_report(scan_result((item,)), (item,))
        markdown = render_markdown(report)
        document = json.loads(render_json(report))

        self.assertIn("## ⛔ Invalid references", markdown)
        self.assertIn("example-org/sample-repo", markdown)
        self.assertIn("| v8 | v7.0.1 |", markdown)
        self.assertEqual("high", document["findings"][0]["severity"])
        self.assertEqual("INVALID_REF", document["findings"][0]["status"])
        self.assertEqual(1, document["summary"]["findings_by_status"]["INVALID_REF"])
        self.assertLess(
            markdown.index("## ⛔ Invalid references"),
            markdown.index("## 🟢 Current references"),
        )

    def test_json_has_schema_version_and_matches_normalized_report(self):
        document = json.loads(render_json(self.report))

        self.assertEqual(1, document["schema_version"])
        self.assertEqual(self.report.summary.to_dict(), document["summary"])
        self.assertEqual(
            [finding.to_dict() for finding in self.report.findings],
            document["findings"],
        )
        self.assertEqual(
            [error.to_dict() for error in self.report.errors], document["errors"]
        )

    def test_rendering_is_deterministic_for_shuffled_input(self):
        reversed_resolutions = tuple(reversed(self.resolutions))
        reversed_warnings = tuple(reversed(self.warnings))
        second_report = build_audit_report(
            scan_result(reversed_resolutions, warnings=reversed_warnings),
            reversed_resolutions,
        )

        self.assertEqual(render_markdown(self.report), render_markdown(second_report))
        self.assertEqual(render_json(self.report), render_json(second_report))
        self.assertNotIn("generated_at", render_json(self.report))

    def test_markdown_escapes_table_content(self):
        item = resolution(
            VersionStatus.CURRENT,
            repository="org/pipe|repo",
            workflow="line\nbreak.yml",
            action="owner/action",
        )
        report = build_audit_report(scan_result((item,)), (item,))

        rendered = render_markdown(report)

        self.assertIn("org/pipe\\|repo", rendered)
        self.assertIn("line break.yml", rendered)

    def test_empty_report_retains_all_sections_and_zero_counts(self):
        report = build_audit_report(
            scan_result((), repositories=0, workflows=0), ()
        )

        markdown = render_markdown(report)
        document = json.loads(render_json(report))

        self.assertEqual([], document["findings"])
        self.assertEqual([], document["errors"])
        self.assertEqual(0, document["summary"]["unique_actions"])
        empty_messages = markdown.count("_No findings._") + markdown.count(
            "_No errors._"
        )
        self.assertEqual(7, empty_messages)

    def test_empty_report_matches_expected_snapshots(self):
        report = build_audit_report(
            scan_result((), repositories=0, workflows=0), ()
        )

        self.assertEqual(
            (FIXTURES / "expected_report.md").read_text(encoding="utf-8"),
            render_markdown(report),
        )
        self.assertEqual(
            (FIXTURES / "expected_report.json").read_text(encoding="utf-8"),
            render_json(report),
        )

    def test_writes_both_report_files_from_same_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markdown_path = root / "nested" / "audit.md"
            json_path = root / "data" / "audit.json"

            write_reports(
                self.report,
                markdown_path=markdown_path,
                json_path=json_path,
            )

            self.assertEqual(
                render_markdown(self.report),
                markdown_path.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                render_json(self.report),
                json_path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
