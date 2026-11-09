import unittest

from scripts.audit_pipeline import resolve_scan_result
from scripts.github_api import GitHubApiError, GitHubNotFoundError
from scripts.models import ActionUsage, CollectionWarning, ScanResult, VersionStatus


class FakeApi:
    def __init__(self, *, failure=None):
        self.failure = failure
        self.calls = []
        self.latest = "v7.0.1"

    def get_paginated(self, path, *, item_key=None, params=None):
        self.calls.append(path)
        if path == "/repos/owner/broken/releases":
            raise self.failure
        if path == "/repos/actions/checkout/releases":
            return iter([{"tag_name": self.latest}])
        raise AssertionError(f"unexpected request: {path}")


def usage(action="actions/checkout"):
    return ActionUsage(
        source_repository="org/source",
        workflow_path=".github/workflows/ci.yml",
        line_number=4,
        raw=f"{action}@v7",
        action_repository=action,
        subpath=None,
        ref="v7",
        kind="github_action",
    )


class AuditPipelineTests(unittest.TestCase):
    def test_preserves_usage_multiplicity_counters_and_both_warning_sources(self):
        api = FakeApi(failure=GitHubApiError(503, "upstream", "unavailable"))
        item = usage()
        warning = CollectionWarning("org/other", None, "collection failed")
        scan = ScanResult((item, item, usage("owner/broken")), (warning,), 5, 8)

        result = resolve_scan_result(api, scan)

        self.assertEqual(5, result.report.summary.repositories_scanned)
        self.assertEqual(8, result.report.summary.workflow_files_scanned)
        self.assertEqual(3, result.report.summary.action_usages)
        self.assertEqual(2, result.report.summary.unique_actions)
        self.assertEqual(2, result.report.summary.errors)
        self.assertCountEqual(
            [VersionStatus.CURRENT, VersionStatus.CURRENT, VersionStatus.UNRESOLVABLE],
            [finding.status for finding in result.report.findings],
        )
        self.assertEqual(
            {"org/other", "org/source"},
            {error.source_repository for error in result.report.errors},
        )
        self.assertEqual((warning,), scan.warnings)
        self.assertEqual(2, result.resolver_telemetry.catalog_lookups)
        self.assertEqual(
            ["/repos/actions/checkout/releases", "/repos/owner/broken/releases"],
            api.calls,
        )

    def test_empty_scan_keeps_collection_warning_without_upstream_requests(self):
        api = FakeApi()
        scan = ScanResult((), (CollectionWarning("org/source", None, "failed"),), 1, 0)

        result = resolve_scan_result(api, scan)

        self.assertEqual((), result.report.findings)
        self.assertEqual(1, result.report.summary.errors)
        self.assertEqual(1, result.report.summary.repositories_scanned)
        self.assertEqual(0, result.resolver_telemetry.catalog_lookups)
        self.assertEqual([], api.calls)

    def test_upstream_404_remains_a_finding_without_an_error(self):
        api = FakeApi(failure=GitHubNotFoundError(404, "upstream", "missing"))

        result = resolve_scan_result(api, ScanResult((usage("owner/broken"),), (), 1, 1))

        self.assertEqual(VersionStatus.UNRESOLVABLE, result.report.findings[0].status)
        self.assertEqual(0, result.report.summary.errors)
        self.assertEqual((), result.report.errors)

    def test_fatal_error_is_propagated_without_a_partial_report(self):
        failure = GitHubApiError(403, "upstream", "forbidden")
        api = FakeApi(failure=failure)

        with self.assertRaises(GitHubApiError) as raised:
            resolve_scan_result(api, ScanResult((usage("owner/broken"),), (), 1, 1))

        self.assertIs(failure, raised.exception)

    def test_each_resolution_pass_uses_a_fresh_cache_and_telemetry(self):
        api = FakeApi()
        scan = ScanResult((usage(),), (), 1, 1)
        first = resolve_scan_result(api, scan)
        api.latest = "v8.0.0"

        second = resolve_scan_result(api, scan)

        self.assertEqual(VersionStatus.CURRENT, first.report.findings[0].status)
        self.assertEqual(VersionStatus.MAJOR_OUTDATED, second.report.findings[0].status)
        self.assertEqual(1, first.resolver_telemetry.catalog_lookups)
        self.assertEqual(1, second.resolver_telemetry.catalog_lookups)
        self.assertEqual(0, second.resolver_telemetry.catalog_cache_hits)
        self.assertEqual(2, len(api.calls))


if __name__ == "__main__":
    unittest.main()
