import unittest

from scripts.collector import RepositoryFilter
from scripts.github_api import GitHubApiError
from scripts.models import RepositoryInfo
from scripts.scanner import scan, scan_repositories


class FakeApi:
    def get_paginated(self, path, *, item_key=None, params=None):
        return iter(
            [
                {
                    "full_name": "org/repo",
                    "default_branch": "main",
                    "archived": False,
                    "fork": False,
                    "private": True,
                }
            ]
        )

    def get_json(self, path, *, params=None):
        return [{"type": "file", "path": ".github/workflows/ci.yml"}]

    def get_text(self, path, *, params=None, accept="application/vnd.github.raw+json"):
        return "steps:\n  - uses: actions/checkout@v4\n"


class ScannerTests(unittest.TestCase):
    def test_scan_connects_collection_and_parser(self):
        result = scan(FakeApi(), RepositoryFilter())

        self.assertEqual(1, result.repositories_scanned)
        self.assertEqual(1, result.workflows_scanned)
        self.assertEqual(1, len(result.usages))
        self.assertEqual("actions/checkout", result.usages[0].action_repository)
        self.assertEqual((), result.warnings)

    def test_repository_5xx_is_non_fatal_partial_failure(self):
        class PartialApi(FakeApi):
            def get_json(self, path, *, params=None):
                raise GitHubApiError(503, path, "temporary")

        result = scan(PartialApi(), RepositoryFilter())

        self.assertEqual(1, result.repositories_scanned)
        self.assertEqual(0, result.workflows_scanned)
        self.assertEqual((), result.usages)
        self.assertEqual(1, len(result.warnings))
        self.assertEqual("org/repo", result.warnings[0].source_repository)

    def test_repository_auth_failure_is_fatal(self):
        class ForbiddenApi(FakeApi):
            def get_json(self, path, *, params=None):
                raise GitHubApiError(403, path, "Forbidden")

        with self.assertRaises(GitHubApiError):
            scan(ForbiddenApi(), RepositoryFilter())

    def test_scans_previously_enumerated_repositories_without_listing_again(self):
        class NoListApi(FakeApi):
            def get_paginated(self, path, *, item_key=None, params=None):
                raise AssertionError("repository inventory must not be listed")

        repository = RepositoryInfo("org/repo", "main", False, False, True)

        result = scan_repositories(NoListApi(), [repository])

        self.assertEqual(1, result.repositories_scanned)
        self.assertEqual(1, len(result.usages))


if __name__ == "__main__":
    unittest.main()
