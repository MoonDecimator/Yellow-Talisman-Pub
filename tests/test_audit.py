import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from scripts.audit import main, run_audit, write_job_summary
from scripts.collector import RepositoryFilter
from scripts.github_api import ApiTelemetry, GitHubApiError
from scripts.models import (
    ActionCatalogEntry,
    ActionUsage,
    AuditReport,
    AuditSummary,
    CollectionWarning,
    RefKind,
    ResolutionResult,
    ScanResult,
    VersionResolution,
    VersionStatus,
)


def usage():
    return ActionUsage(
        source_repository="org/source",
        workflow_path=".github/workflows/ci.yml",
        line_number=4,
        raw="actions/checkout@v6",
        action_repository="actions/checkout",
        subpath=None,
        ref="v6",
        kind="github_action",
    )


class AuditTests(unittest.TestCase):
    @patch("scripts.audit.write_reports")
    @patch("scripts.audit_pipeline.VersionResolver")
    @patch("scripts.audit.scan")
    def test_pipeline_combines_partial_warnings_before_rendering(
        self, scan_mock, resolver_type, write_reports_mock
    ):
        item = usage()
        scan_mock.return_value = ScanResult(
            (item,),
            (CollectionWarning("org/one", None, "collection failed"),),
            2,
            1,
        )
        catalog = ActionCatalogEntry(
            "actions/checkout", "v7.0.1", None, "release", True
        )
        resolver_type.return_value.resolve_with_warnings.return_value = ResolutionResult(
            (VersionResolution(item, RefKind.MAJOR_TAG, VersionStatus.MAJOR_OUTDATED, catalog),),
            (CollectionWarning("org/source", item.workflow_path, "lookup failed"),),
        )

        report = run_audit(object(), RepositoryFilter())

        self.assertEqual(2, report.summary.errors)
        self.assertEqual(1, report.summary.action_usages)
        write_reports_mock.assert_called_once()

    def test_missing_token_is_fatal(self):
        self.assertEqual(1, main([], environ={}))

    @patch("scripts.audit.run_audit")
    def test_api_failure_is_fatal(self, run_audit_mock):
        run_audit_mock.side_effect = GitHubApiError(403, "url", "Forbidden")

        self.assertEqual(1, main([], environ={"WATCHTOWER_TOKEN": "token"}))

    @patch("scripts.audit.run_audit")
    def test_partial_errors_are_non_fatal(self, run_audit_mock):
        run_audit_mock.return_value = AuditReport(
            AuditSummary(1, 0, 0, 0, (), (), 1),
            (),
            (),
        )

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(
                [], environ={"WATCHTOWER_TOKEN": "super-secret-value"}
            )

        self.assertEqual(0, exit_code)
        self.assertNotIn("super-secret-value", stderr.getvalue())

    @patch("scripts.audit.run_audit")
    def test_cli_passes_repeatable_include_filter(self, run_audit_mock):
        run_audit_mock.return_value = AuditReport(
            AuditSummary(2, 0, 0, 0, (), (), 0),
            (),
            (),
        )

        exit_code = main(
            ["--include", "org/one", "--include", "two"],
            environ={"WATCHTOWER_TOKEN": "token"},
        )

        self.assertEqual(0, exit_code)
        policy = run_audit_mock.call_args.args[1]
        self.assertEqual(
            frozenset({"org/one", "two"}), policy.included_repositories
        )

    def test_job_summary_contains_counts_and_rate_limit_telemetry(self):
        report = AuditReport(
            AuditSummary(
                repositories_scanned=2,
                workflow_files_scanned=3,
                action_usages=4,
                unique_actions=1,
                findings_by_severity=(
                    ("high", 1),
                    ("medium", 0),
                    ("low", 0),
                    ("info", 3),
                ),
                findings_by_status=(("MAJOR_OUTDATED", 1), ("CURRENT", 3)),
                errors=1,
            ),
            (),
            (),
        )
        telemetry = ApiTelemetry(12, 2, 4988, 123456)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.md"

            write_job_summary(path, report, telemetry)

            content = path.read_text(encoding="utf-8")
        self.assertIn("Repositories scanned | 2", content)
        self.assertIn("Requests: 12", content)
        self.assertIn("Retries: 2", content)
        self.assertIn("Rate limit remaining: 4988", content)
        self.assertIn("`MAJOR_OUTDATED` | 1", content)
        self.assertNotIn("super-secret-value", content)


if __name__ == "__main__":
    unittest.main()
