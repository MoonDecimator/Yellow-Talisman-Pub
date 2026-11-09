import unittest

from scripts.collector import RepositoryCollector, RepositoryFilter, WorkflowCollector
from scripts.github_api import GitHubApiError, GitHubNotFoundError
from scripts.models import RepositoryInfo


class FakeApi:
    def __init__(self, *, repositories=(), directory=None, raw=None):
        self.repositories = repositories
        self.directory = directory
        self.raw = raw or {}
        self.calls = []

    def get_paginated(self, path, *, item_key=None, params=None):
        self.calls.append(("paginated", path, item_key, params))
        return iter(self.repositories)

    def get_json(self, path, *, params=None):
        self.calls.append(("json", path, params))
        if isinstance(self.directory, Exception):
            raise self.directory
        return self.directory

    def get_text(self, path, *, params=None, accept="application/vnd.github.raw+json"):
        self.calls.append(("text", path, params, accept))
        result = self.raw[path]
        if isinstance(result, Exception):
            raise result
        return result


def repository(name="org/repo", **overrides):
    values = {
        "full_name": name,
        "default_branch": "main",
        "archived": False,
        "fork": False,
        "private": True,
    }
    values.update(overrides)
    return RepositoryInfo(**values)


class RepositoryCollectorTests(unittest.TestCase):
    def test_enumerates_and_sorts_installation_repositories(self):
        api = FakeApi(
            repositories=[
                {
                    "full_name": "org/Zebra",
                    "default_branch": "main",
                    "archived": False,
                    "fork": False,
                    "private": True,
                },
                {
                    "full_name": "org/alpha",
                    "default_branch": "trunk",
                    "archived": False,
                    "fork": False,
                    "private": False,
                },
            ]
        )

        result = RepositoryCollector(api).list_repositories()

        self.assertEqual(["org/alpha", "org/Zebra"], [item.full_name for item in result])

    def test_filter_excludes_archived_forks_and_explicit_names(self):
        policy = RepositoryFilter(excluded_repositories=frozenset({"skip", "org/full"}))

        self.assertFalse(policy.includes(repository("org/archived", archived=True)))
        self.assertFalse(policy.includes(repository("org/fork", fork=True)))
        self.assertFalse(policy.includes(repository("org/skip")))
        self.assertFalse(policy.includes(repository("org/full")))
        self.assertTrue(policy.includes(repository("org/keep")))

    def test_filter_can_include_archived_and_forks(self):
        policy = RepositoryFilter(include_archived=True, include_forks=True)

        self.assertTrue(policy.includes(repository("org/archived", archived=True)))
        self.assertTrue(policy.includes(repository("org/fork", fork=True)))

    def test_filter_includes_only_explicit_full_or_short_names(self):
        policy = RepositoryFilter(
            included_repositories=frozenset({"ORG/ONE", "two"})
        )

        self.assertTrue(policy.includes(repository("org/one")))
        self.assertTrue(policy.includes(repository("org/TWO")))
        self.assertFalse(policy.includes(repository("org/three")))

    def test_exclude_takes_precedence_over_include(self):
        policy = RepositoryFilter(
            included_repositories=frozenset({"org/repo"}),
            excluded_repositories=frozenset({"org/repo"}),
        )

        self.assertFalse(policy.includes(repository("org/repo")))


class WorkflowCollectorTests(unittest.TestCase):
    def test_directory_404_is_no_workflows(self):
        not_found = GitHubNotFoundError(404, "url", "Not Found")
        collector = WorkflowCollector(FakeApi(directory=not_found))

        self.assertEqual((), collector.list_workflow_paths(repository()))

    def test_empty_directory_is_no_workflows(self):
        collector = WorkflowCollector(FakeApi(directory=[]))

        self.assertEqual((), collector.list_workflow_paths(repository()))

    def test_lists_only_yaml_workflow_files_in_deterministic_order(self):
        api = FakeApi(
            directory=[
                {"type": "file", "path": ".github/workflows/z.yaml"},
                {"type": "file", "path": ".github/workflows/a.yml"},
                {"type": "file", "path": ".github/workflows/readme.md"},
                {"type": "dir", "path": ".github/workflows/nested.yml"},
            ]
        )

        paths = WorkflowCollector(api).list_workflow_paths(repository())

        self.assertEqual(
            (".github/workflows/a.yml", ".github/workflows/z.yaml"), paths
        )

    def test_fetches_raw_content_from_default_branch(self):
        path = "/repos/org/repo/contents/.github/workflows/ci.yml"
        api = FakeApi(raw={path: "name: CI\n"})

        workflow = WorkflowCollector(api).fetch_workflow(
            repository(), ".github/workflows/ci.yml"
        )

        self.assertEqual("name: CI\n", workflow.content)
        self.assertEqual(
            ("text", path, {"ref": "main"}, "application/vnd.github.raw+json"),
            api.calls[0],
        )

    def test_file_404_is_recoverable_warning(self):
        path = "/repos/org/repo/contents/.github/workflows/ci.yml"
        not_found = GitHubNotFoundError(404, "url", "Not Found")
        api = FakeApi(
            directory=[{"type": "file", "path": ".github/workflows/ci.yml"}],
            raw={path: not_found},
        )

        workflows, warnings = WorkflowCollector(api).collect(repository())

        self.assertEqual((), workflows)
        self.assertEqual(1, len(warnings))
        self.assertEqual(".github/workflows/ci.yml", warnings[0].workflow_path)

    def test_file_5xx_is_recoverable_and_collection_continues(self):
        first = "/repos/org/repo/contents/.github/workflows/a.yml"
        second = "/repos/org/repo/contents/.github/workflows/b.yml"
        api = FakeApi(
            directory=[
                {"type": "file", "path": ".github/workflows/a.yml"},
                {"type": "file", "path": ".github/workflows/b.yml"},
            ],
            raw={
                first: GitHubApiError(503, first, "temporary"),
                second: "name: B\n",
            },
        )

        workflows, warnings = WorkflowCollector(api).collect(repository())

        self.assertEqual(
            [".github/workflows/b.yml"], [item.path for item in workflows]
        )
        self.assertEqual(
            [".github/workflows/a.yml"],
            [item.workflow_path for item in warnings],
        )

    def test_file_auth_failure_is_fatal(self):
        path = "/repos/org/repo/contents/.github/workflows/ci.yml"
        api = FakeApi(
            directory=[{"type": "file", "path": ".github/workflows/ci.yml"}],
            raw={path: GitHubApiError(403, path, "Forbidden")},
        )

        with self.assertRaises(GitHubApiError):
            WorkflowCollector(api).collect(repository())


if __name__ == "__main__":
    unittest.main()
