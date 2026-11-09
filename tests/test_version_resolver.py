import unittest

from scripts.github_api import GitHubApiError, GitHubNotFoundError
from scripts.models import ActionUsage, RefKind, SemanticVersion, VersionStatus
from scripts.version_resolver import (
    VersionResolver,
    classify_static_ref,
    parse_semver,
)


def usage(action="actions/checkout", ref="v7", *, line=1):
    return ActionUsage(
        source_repository="org/source",
        workflow_path=".github/workflows/ci.yml",
        line_number=line,
        raw=f"{action}@{ref}",
        action_repository=action,
        subpath=None,
        ref=ref,
        kind="github_action",
    )


class FakeApi:
    def __init__(self, *, releases=None, tags=None, branches=(), tag_refs=()):
        self.releases = releases or {}
        self.tags = tags or {}
        self.branches = set(branches)
        self.tag_refs = set(tag_refs)
        self.calls = []
        self.branch_errors = {}

    def get_paginated(self, path, *, item_key=None, params=None):
        self.calls.append(("paginated", path))
        collection = self.tags if path.endswith("/tags") else self.releases
        result = collection.get(path, [])
        if isinstance(result, Exception):
            raise result
        return iter(result)

    def get_json(self, path, *, params=None):
        self.calls.append(("json", path))
        if path in self.branch_errors:
            raise self.branch_errors[path]
        if path in self.tag_refs:
            return {"ref": "refs/tags/" + path.split("/git/ref/tags/", 1)[1]}
        if path not in self.branches:
            raise GitHubNotFoundError(404, path, "Not Found")
        return {"name": path.rsplit("/", 1)[-1]}


def stable_release(tag):
    return {"tag_name": tag, "draft": False, "prerelease": False}


class SemVerTests(unittest.TestCase):
    def test_parses_and_normalizes_full_stable_versions(self):
        self.assertEqual(SemanticVersion(7, 0, 1), parse_semver("v7.0.1"))
        self.assertEqual(SemanticVersion(7, 0, 1), parse_semver("7.0.1"))

    def test_rejects_prerelease_shortened_and_leading_zero_versions(self):
        for value in ("v8.0.0-beta.1", "v8.0.0-rc.2", "v7.0", "v07.0.1"):
            with self.subTest(value=value):
                self.assertIsNone(parse_semver(value))

    def test_major_tag_is_integer_only_and_does_not_capture_semver(self):
        self.assertEqual((RefKind.MAJOR_TAG, 7), classify_static_ref("v7"))
        self.assertEqual((RefKind.MAJOR_TAG, 7), classify_static_ref("7"))
        self.assertEqual(
            (RefKind.SEMVER, SemanticVersion(7, 0, 1)),
            classify_static_ref("v7.0.1"),
        )

    def test_recognizes_only_full_forty_character_sha(self):
        sha = "aB" * 20
        self.assertEqual((RefKind.SHA, None), classify_static_ref(sha))
        self.assertIsNone(classify_static_ref(sha[:-1]))


class CatalogTests(unittest.TestCase):
    def test_selects_latest_stable_release_and_excludes_draft_and_prerelease(self):
        path = "/repos/actions/checkout/releases"
        api = FakeApi(
            releases={
                path: [
                    stable_release("v7.0.1"),
                    {"tag_name": "v9.0.0", "draft": True, "prerelease": False},
                    {"tag_name": "v8.0.0", "draft": False, "prerelease": True},
                    stable_release("not-semver"),
                    stable_release("v6.2.0"),
                ]
            }
        )

        entry = VersionResolver(api).build_catalog([usage()])[0]

        self.assertEqual("v7.0.1", entry.latest_stable)
        self.assertEqual(SemanticVersion(7, 0, 1), entry.latest_version)
        self.assertEqual("release", entry.source)
        self.assertTrue(entry.repository_available)
        self.assertNotIn(("paginated", "/repos/actions/checkout/tags"), api.calls)

    def test_falls_back_to_latest_stable_tag_without_usable_release(self):
        releases_path = "/repos/owner/action/releases"
        tags_path = "/repos/owner/action/tags"
        api = FakeApi(
            releases={
                releases_path: [
                    {"tag_name": "v3.0.0-rc.1", "prerelease": True}
                ]
            },
            tags={
                tags_path: [
                    {"name": "v2.1.0"},
                    {"name": "v2.2.0"},
                    {"name": "v3.0.0-beta.1"},
                ]
            },
        )

        entry = VersionResolver(api).build_catalog([usage("owner/action")])[0]

        self.assertEqual("v2.2.0", entry.latest_stable)
        self.assertEqual(SemanticVersion(2, 2, 0), entry.latest_version)
        self.assertEqual("tag", entry.source)
        self.assertTrue(entry.repository_available)
        self.assertEqual(
            [("paginated", releases_path), ("paginated", tags_path)], api.calls
        )

    def test_no_semver_in_releases_or_tags_is_unresolvable(self):
        api = FakeApi(
            releases={"/repos/owner/action/releases": [stable_release("stable")]},
            tags={"/repos/owner/action/tags": [{"name": "latest"}]},
        )

        result = VersionResolver(api).resolve([usage("owner/action", "v1")])[0]

        self.assertEqual(VersionStatus.UNRESOLVABLE, result.status)
        self.assertIsNone(result.catalog.latest_version)
        self.assertTrue(result.catalog.repository_available)

    def test_upstream_404_is_unresolvable_and_does_not_abort(self):
        not_found = GitHubNotFoundError(404, "url", "Not Found")
        api = FakeApi(releases={"/repos/missing/action/releases": not_found})

        result = VersionResolver(api).resolve([usage("missing/action", "v1")])[0]

        self.assertEqual(VersionStatus.UNRESOLVABLE, result.status)
        self.assertFalse(result.catalog.repository_available)

    def test_arbitrary_ref_in_missing_upstream_is_unresolvable(self):
        not_found = GitHubNotFoundError(404, "url", "Not Found")
        api = FakeApi(releases={"/repos/missing/action/releases": not_found})

        result = VersionResolver(api).resolve(
            [usage("missing/action", "develop")]
        )[0]

        self.assertEqual(VersionStatus.UNRESOLVABLE, result.status)
        self.assertNotIn(
            ("json", "/repos/missing/action/branches/develop"), api.calls
        )

    def test_sha_in_missing_upstream_is_unresolvable(self):
        not_found = GitHubNotFoundError(404, "url", "Not Found")
        api = FakeApi(releases={"/repos/missing/action/releases": not_found})

        result = VersionResolver(api).resolve(
            [usage("missing/action", "a" * 40)]
        )[0]

        self.assertEqual(RefKind.SHA, result.ref_kind)
        self.assertEqual(VersionStatus.UNRESOLVABLE, result.status)

    def test_non_404_release_api_failure_is_not_hidden(self):
        path = "/repos/owner/action/releases"
        api = FakeApi(
            releases={path: GitHubApiError(403, path, "Forbidden")}
        )

        with self.assertRaises(GitHubApiError):
            VersionResolver(api).resolve([usage("owner/action", "v1")])

    def test_non_404_tags_api_failure_is_not_hidden(self):
        path = "/repos/owner/action/tags"
        api = FakeApi(tags={path: GitHubApiError(500, path, "Server Error")})

        with self.assertRaises(GitHubApiError):
            VersionResolver(api).resolve([usage("owner/action", "v1")])

    def test_tolerant_resolution_keeps_other_actions_after_5xx(self):
        failed_path = "/repos/broken/action/releases"
        working_path = "/repos/working/action/releases"
        api = FakeApi(
            releases={
                failed_path: GitHubApiError(503, failed_path, "temporary"),
                working_path: [stable_release("v2.0.0")],
            }
        )

        result = VersionResolver(api).resolve_with_warnings(
            [usage("broken/action", "v1"), usage("working/action", "v2")]
        )

        self.assertEqual(
            [VersionStatus.UNRESOLVABLE, VersionStatus.CURRENT],
            [item.status for item in result.resolutions],
        )
        self.assertEqual(1, len(result.warnings))
        self.assertIn("broken/action", result.warnings[0].reason)

    def test_tolerant_resolution_deduplicates_warnings_by_workflow(self):
        path = "/repos/broken/action/releases"
        api = FakeApi(releases={path: GitHubApiError(500, path, "temporary")})

        result = VersionResolver(api).resolve_with_warnings(
            [
                usage("broken/action", "v1", line=1),
                usage("broken/action", "v2", line=2),
            ]
        )

        self.assertEqual(2, len(result.resolutions))
        self.assertEqual(1, len(result.warnings))

    def test_tolerant_resolution_keeps_auth_failure_fatal(self):
        path = "/repos/owner/action/releases"
        api = FakeApi(releases={path: GitHubApiError(403, path, "Forbidden")})

        with self.assertRaises(GitHubApiError):
            VersionResolver(api).resolve_with_warnings(
                [usage("owner/action", "v1")]
            )

    def test_deduplicates_case_insensitive_action_repository_lookups(self):
        path = "/repos/Actions/Checkout/releases"
        api = FakeApi(releases={path: [stable_release("v7.0.1")]})
        usages = [
            usage("Actions/Checkout", "v7", line=1),
            usage("actions/checkout", "v6", line=2),
            usage("Actions/Checkout", "v7.0.0", line=3),
        ]

        results = VersionResolver(api).resolve(usages)

        self.assertEqual(3, len(results))
        self.assertEqual(1, api.calls.count(("paginated", path)))

    def test_twenty_repository_usages_share_one_catalog_lookup(self):
        path = "/repos/actions/checkout/releases"
        api = FakeApi(releases={path: [stable_release("v7.0.1")]})
        usages = [
            ActionUsage(
                source_repository=f"org/repository-{index:02d}",
                workflow_path=".github/workflows/ci.yml",
                line_number=1,
                raw="actions/checkout@v7",
                action_repository=(
                    "Actions/Checkout" if index % 2 else "actions/checkout"
                ),
                subpath=None,
                ref="v7",
                kind="github_action",
            )
            for index in range(20)
        ]
        resolver = VersionResolver(api)

        results = resolver.resolve(usages)

        self.assertEqual(20, len(results))
        self.assertEqual(1, resolver.telemetry.catalog_lookups)
        self.assertEqual(1, api.calls.count(("paginated", path)))

    def test_reuses_catalog_cache_across_resolve_calls(self):
        path = "/repos/actions/checkout/releases"
        api = FakeApi(releases={path: [stable_release("v7.0.1")]})
        resolver = VersionResolver(api)

        resolver.resolve([usage(ref="v7")])
        resolver.resolve([usage(ref="v6")])

        self.assertEqual(1, api.calls.count(("paginated", path)))
        self.assertEqual(1, resolver.telemetry.catalog_lookups)
        self.assertEqual(1, resolver.telemetry.catalog_cache_hits)


class StatusTests(unittest.TestCase):
    def resolve(self, ref, latest="v7.0.1"):
        api = FakeApi(
            releases={
                "/repos/actions/checkout/releases": [stable_release(latest)]
            }
        )
        return VersionResolver(api).resolve([usage(ref=ref)])[0]

    def test_major_tag_status(self):
        self.assertEqual(VersionStatus.MAJOR_OUTDATED, self.resolve("v3").status)
        self.assertEqual(VersionStatus.CURRENT, self.resolve("v7").status)
        self.assertEqual(VersionStatus.CURRENT, self.resolve("7").status)

    def test_exact_semver_outdated_statuses(self):
        cases = (
            ("v7.0.0", "v7.0.1", VersionStatus.PATCH_OUTDATED),
            ("v7.0.0", "v7.2.0", VersionStatus.MINOR_OUTDATED),
            ("v6.5.0", "v7.0.1", VersionStatus.MAJOR_OUTDATED),
            ("v7.0.1", "v7.0.1", VersionStatus.CURRENT),
            ("v8.0.0", "v7.0.1", VersionStatus.INVALID_REF),
        )
        for current, latest, expected in cases:
            with self.subTest(current=current, latest=latest):
                self.assertEqual(expected, self.resolve(current, latest).status)

    def test_sha_is_pinned_even_when_upstream_version_is_unavailable(self):
        result = VersionResolver(FakeApi()).resolve([usage(ref="a" * 40)])[0]

        self.assertEqual(RefKind.SHA, result.ref_kind)
        self.assertEqual(VersionStatus.SHA_PINNED, result.status)

    def test_semver_is_not_sent_to_branch_lookup(self):
        api = FakeApi(
            releases={
                "/repos/actions/checkout/releases": [stable_release("v7.0.1")]
            }
        )

        result = VersionResolver(api).resolve([usage(ref="v7.0.0")])[0]

        self.assertEqual(RefKind.SEMVER, result.ref_kind)
        self.assertFalse(any(method == "json" for method, _ in api.calls))

    def test_nonexistent_future_checkout_v8_is_invalid(self):
        api = FakeApi(
            releases={
                "/repos/actions/checkout/releases": [stable_release("v7.0.1")]
            }
        )
        result = VersionResolver(api).resolve([usage(ref="v8")])[0]

        self.assertEqual(RefKind.MAJOR_TAG, result.ref_kind)
        self.assertEqual(VersionStatus.INVALID_REF, result.status)
        self.assertIn(
            ("json", "/repos/actions/checkout/git/ref/tags/v8"), api.calls
        )
        self.assertIn(
            ("json", "/repos/actions/checkout/branches/v8"), api.calls
        )

    def test_nonexistent_future_patch_and_major_are_invalid(self):
        api = FakeApi(
            releases={
                "/repos/actions/checkout/releases": [stable_release("v7.0.1")]
            }
        )
        results = VersionResolver(api).resolve(
            [usage(ref="v7.0.2"), usage(ref="v9999")]
        )
        self.assertEqual(
            [VersionStatus.INVALID_REF, VersionStatus.INVALID_REF],
            [item.status for item in results],
        )

    def test_existing_future_tag_is_not_falsely_reported_invalid(self):
        paths = {
            "/repos/actions/checkout/git/ref/tags/v8",
            "/repos/actions/checkout/git/ref/tags/v8.0.0",
        }
        api = FakeApi(
            releases={
                "/repos/actions/checkout/releases": [stable_release("v7.0.1")]
            },
            tag_refs=paths,
        )
        results = VersionResolver(api).resolve(
            [usage(ref="v8"), usage(ref="v8.0.0")]
        )
        self.assertEqual(
            [VersionStatus.CURRENT, VersionStatus.CURRENT],
            [item.status for item in results],
        )
        self.assertFalse(any("/branches/" in path for _, path in api.calls))

    def test_future_numeric_branch_is_floating_not_invalid(self):
        api = FakeApi(
            releases={
                "/repos/actions/checkout/releases": [stable_release("v7.0.1")]
            },
            branches={"/repos/actions/checkout/branches/v8"},
        )
        result = VersionResolver(api).resolve([usage(ref="v8")])[0]
        self.assertEqual(RefKind.BRANCH, result.ref_kind)
        self.assertEqual(VersionStatus.FLOATING_BRANCH, result.status)

    def test_nonexistent_future_tag_lookup_is_cached_across_usages(self):
        api = FakeApi(
            releases={
                "/repos/actions/checkout/releases": [stable_release("v7.0.1")]
            }
        )
        resolver = VersionResolver(api)
        results = resolver.resolve([usage(ref="v8"), usage(ref="v8", line=2)])
        resolver.resolve([usage(ref="v8", line=3)])
        self.assertTrue(all(x.status is VersionStatus.INVALID_REF for x in results))
        self.assertEqual(
            1, api.calls.count(("json", "/repos/actions/checkout/git/ref/tags/v8"))
        )
        self.assertEqual(
            1, api.calls.count(("json", "/repos/actions/checkout/branches/v8"))
        )

    def test_future_tag_api_failure_is_not_reported_as_invalid(self):
        path = "/repos/actions/checkout/git/ref/tags/v8"
        api = FakeApi(
            releases={
                "/repos/actions/checkout/releases": [stable_release("v7.0.1")]
            }
        )
        api.branch_errors[path] = GitHubApiError(403, path, "Forbidden")
        with self.assertRaises(GitHubApiError):
            VersionResolver(api).resolve([usage(ref="v8")])


class BranchClassificationTests(unittest.TestCase):
    def test_existing_non_default_branch_is_floating(self):
        branch_path = "/repos/owner/action/branches/release%2Fnext"
        api = FakeApi(branches={branch_path})

        result = VersionResolver(api).resolve(
            [usage("owner/action", "release/next")]
        )[0]

        self.assertEqual(RefKind.BRANCH, result.ref_kind)
        self.assertEqual(VersionStatus.FLOATING_BRANCH, result.status)
        self.assertIn(("json", branch_path), api.calls)

    def test_missing_branch_is_unknown_ref(self):
        result = VersionResolver(FakeApi()).resolve(
            [usage("owner/action", "stable")]
        )[0]

        self.assertEqual(RefKind.ARBITRARY, result.ref_kind)
        self.assertEqual(VersionStatus.UNKNOWN_REF, result.status)

    def test_main_is_verified_instead_of_assumed_to_be_a_branch(self):
        result = VersionResolver(FakeApi()).resolve(
            [usage("owner/action", "main")]
        )[0]

        self.assertEqual(VersionStatus.UNKNOWN_REF, result.status)

    def test_branch_lookup_is_cached_for_same_action_and_ref(self):
        branch_path = "/repos/owner/action/branches/develop"
        api = FakeApi(branches={branch_path})
        resolver = VersionResolver(api)

        results = resolver.resolve(
            [
                usage("owner/action", "develop", line=1),
                usage("owner/action", "develop", line=2),
            ]
        )

        self.assertTrue(
            all(result.status is VersionStatus.FLOATING_BRANCH for result in results)
        )
        self.assertEqual(1, api.calls.count(("json", branch_path)))

    def test_missing_branch_lookup_is_cached(self):
        branch_path = "/repos/owner/action/branches/stable"
        api = FakeApi()

        results = VersionResolver(api).resolve(
            [
                usage("owner/action", "stable", line=1),
                usage("owner/action", "stable", line=2),
            ]
        )

        self.assertTrue(
            all(result.status is VersionStatus.UNKNOWN_REF for result in results)
        )
        self.assertEqual(1, api.calls.count(("json", branch_path)))

    def test_branch_telemetry_counts_unique_lookups_and_cache_hits(self):
        resolver = VersionResolver(FakeApi())

        resolver.resolve(
            [
                usage("owner/action", "stable", line=1),
                usage("owner/action", "stable", line=2),
            ]
        )

        self.assertEqual(1, resolver.telemetry.branch_lookups)
        self.assertEqual(1, resolver.telemetry.branch_cache_hits)

    def test_same_ref_in_different_actions_has_separate_branch_lookup(self):
        paths = {
            "/repos/owner/one/branches/develop",
            "/repos/owner/two/branches/develop",
        }
        api = FakeApi(branches=paths)

        VersionResolver(api).resolve(
            [usage("owner/one", "develop"), usage("owner/two", "develop")]
        )

        self.assertEqual(
            paths,
            {path for method, path in api.calls if method == "json"},
        )

    def test_non_404_branch_api_failure_is_not_hidden(self):
        path = "/repos/owner/action/branches/develop"
        api = FakeApi()
        api.branch_errors[path] = GitHubApiError(403, path, "Forbidden")

        with self.assertRaises(GitHubApiError):
            VersionResolver(api).resolve([usage("owner/action", "develop")])


if __name__ == "__main__":
    unittest.main()
