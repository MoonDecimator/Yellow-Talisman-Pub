"""Resolve collected GitHub Action refs against upstream stable versions."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from .github_api import (
    GitHubApi,
    GitHubApiError,
    GitHubNotFoundError,
    is_fatal_api_error,
)
from .models import (
    ActionCatalogEntry,
    ActionUsage,
    CollectionWarning,
    RefKind,
    ResolutionResult,
    SemanticVersion,
    VersionResolution,
    VersionStatus,
)


SEMVER = re.compile(
    r"^v?(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)$"
)
MAJOR_TAG = re.compile(r"^v?(?P<major>0|[1-9][0-9]*)$")
FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


@dataclass(frozen=True, slots=True)
class ResolverTelemetry:
    """Unique upstream lookups and cache reuse observed by the resolver."""

    catalog_lookups: int
    catalog_cache_hits: int
    branch_lookups: int
    branch_cache_hits: int


def parse_semver(value: str) -> SemanticVersion | None:
    """Parse a full stable SemVer, optionally prefixed with ``v``."""

    match = SEMVER.fullmatch(value)
    if match is None:
        return None
    return SemanticVersion(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
    )


def classify_static_ref(
    ref: str,
) -> tuple[RefKind, SemanticVersion | int | None] | None:
    """Classify refs that do not require a GitHub branch lookup."""

    if FULL_SHA.fullmatch(ref):
        return RefKind.SHA, None

    major_match = MAJOR_TAG.fullmatch(ref)
    if major_match is not None:
        return RefKind.MAJOR_TAG, int(major_match.group("major"))

    version = parse_semver(ref)
    if version is not None:
        return RefKind.SEMVER, version
    return None


class VersionResolver:
    """Build a deduplicated Action catalog and classify collected usages."""

    def __init__(self, api: GitHubApi) -> None:
        self._api = api
        self._catalog_cache: dict[str, ActionCatalogEntry] = {}
        self._branch_cache: dict[tuple[str, str], bool] = {}
        self._tag_cache: dict[tuple[str, str], bool] = {}
        self._catalog_lookups = 0
        self._catalog_cache_hits = 0
        self._branch_lookups = 0
        self._branch_cache_hits = 0

    @property
    def telemetry(self) -> ResolverTelemetry:
        """Return deduplication counters without exposing request credentials."""

        return ResolverTelemetry(
            catalog_lookups=self._catalog_lookups,
            catalog_cache_hits=self._catalog_cache_hits,
            branch_lookups=self._branch_lookups,
            branch_cache_hits=self._branch_cache_hits,
        )

    def build_catalog(
        self, usages: Iterable[ActionUsage]
    ) -> tuple[ActionCatalogEntry, ...]:
        """Resolve each case-insensitive Action repository at most once."""

        repositories: dict[str, str] = {}
        for usage in usages:
            repositories.setdefault(
                usage.action_repository.casefold(), usage.action_repository
            )

        entries = [
            self._catalog_entry(repositories[key]) for key in sorted(repositories)
        ]
        return tuple(entries)

    def resolve(
        self, usages: Iterable[ActionUsage]
    ) -> tuple[VersionResolution, ...]:
        """Resolve usages while preserving their input order."""

        usage_list = tuple(usages)
        catalog = {
            entry.action_repository.casefold(): entry
            for entry in self.build_catalog(usage_list)
        }
        return tuple(
            self._resolve_usage(usage, catalog[usage.action_repository.casefold()])
            for usage in usage_list
        )

    def resolve_with_warnings(
        self, usages: Iterable[ActionUsage]
    ) -> ResolutionResult:
        """Resolve independent Actions while retaining recoverable API failures."""

        usage_list = tuple(usages)
        groups: dict[str, list[tuple[int, ActionUsage]]] = {}
        for index, item in enumerate(usage_list):
            groups.setdefault(item.action_repository.casefold(), []).append(
                (index, item)
            )

        resolutions: list[VersionResolution | None] = [None] * len(usage_list)
        warnings: list[CollectionWarning] = []
        for key in sorted(groups):
            indexed_usages = groups[key]
            action_usages = tuple(item for _, item in indexed_usages)
            try:
                action_resolutions = self.resolve(action_usages)
            except GitHubApiError as error:
                if is_fatal_api_error(error):
                    raise
                catalog = ActionCatalogEntry(
                    action_usages[0].action_repository,
                    None,
                    None,
                    None,
                    False,
                )
                action_resolutions = tuple(
                    _unresolvable_resolution(item, catalog)
                    for item in action_usages
                )
                warning_locations = {
                    (item.source_repository, item.workflow_path)
                    for item in action_usages
                }
                warnings.extend(
                    CollectionWarning(
                        source_repository,
                        workflow_path,
                        f"upstream {catalog.action_repository} lookup failed: {error}",
                    )
                    for source_repository, workflow_path in sorted(
                        warning_locations,
                        key=lambda location: (
                            location[0].casefold(),
                            location[1].casefold(),
                        ),
                    )
                )

            for (index, _), resolution in zip(
                indexed_usages, action_resolutions, strict=True
            ):
                resolutions[index] = resolution

        return ResolutionResult(
            resolutions=tuple(
                item for item in resolutions if item is not None
            ),
            warnings=tuple(warnings),
        )

    def _catalog_entry(self, action_repository: str) -> ActionCatalogEntry:
        key = action_repository.casefold()
        cached = self._catalog_cache.get(key)
        if cached is not None:
            self._catalog_cache_hits += 1
            return cached

        self._catalog_lookups += 1
        encoded_repository = quote(action_repository, safe="/")
        releases_path = f"/repos/{encoded_repository}/releases"
        try:
            release_versions = _version_candidates(
                self._api.get_paginated(releases_path), "tag_name"
            )
        except GitHubNotFoundError:
            entry = ActionCatalogEntry(action_repository, None, None, None, False)
        else:
            if release_versions:
                tag, version = max(release_versions, key=lambda item: item[1])
                entry = ActionCatalogEntry(
                    action_repository, tag, version, "release", True
                )
            else:
                entry = self._catalog_from_tags(action_repository, encoded_repository)

        self._catalog_cache[key] = entry
        return entry

    def _catalog_from_tags(
        self, action_repository: str, encoded_repository: str
    ) -> ActionCatalogEntry:
        try:
            tag_versions = _version_candidates(
                self._api.get_paginated(f"/repos/{encoded_repository}/tags"), "name"
            )
        except GitHubNotFoundError:
            return ActionCatalogEntry(action_repository, None, None, None, False)
        if not tag_versions:
            return ActionCatalogEntry(action_repository, None, None, None, True)
        tag, version = max(tag_versions, key=lambda item: item[1])
        return ActionCatalogEntry(action_repository, tag, version, "tag", True)

    def _resolve_usage(
        self, usage: ActionUsage, catalog: ActionCatalogEntry
    ) -> VersionResolution:
        static = classify_static_ref(usage.ref)
        if not catalog.repository_available:
            ref_kind = static[0] if static is not None else RefKind.ARBITRARY
            return VersionResolution(
                usage, ref_kind, VersionStatus.UNRESOLVABLE, catalog
            )

        if static is None:
            is_branch = self._branch_exists(usage.action_repository, usage.ref)
            ref_kind = RefKind.BRANCH if is_branch else RefKind.ARBITRARY
            status = (
                VersionStatus.FLOATING_BRANCH
                if is_branch
                else VersionStatus.UNKNOWN_REF
            )
            return VersionResolution(usage, ref_kind, status, catalog)

        ref_kind, current = static
        if ref_kind is RefKind.SHA:
            return VersionResolution(
                usage, ref_kind, VersionStatus.SHA_PINNED, catalog
            )
        if catalog.latest_version is None:
            return VersionResolution(
                usage, ref_kind, VersionStatus.UNRESOLVABLE, catalog
            )
        if ref_kind is RefKind.MAJOR_TAG:
            assert isinstance(current, int)
            if current < catalog.latest_version.major:
                status = VersionStatus.MAJOR_OUTDATED
            elif current > catalog.latest_version.major:
                return self._resolve_future_ref(usage, ref_kind, catalog)
            else:
                status = VersionStatus.CURRENT
            return VersionResolution(usage, ref_kind, status, catalog)

        assert isinstance(current, SemanticVersion)
        if current > catalog.latest_version:
            return self._resolve_future_ref(usage, ref_kind, catalog)
        status = _compare_exact_version(current, catalog.latest_version)
        return VersionResolution(usage, ref_kind, status, catalog)

    def _resolve_future_ref(
        self, usage: ActionUsage, ref_kind: RefKind, catalog: ActionCatalogEntry
    ) -> VersionResolution:
        """Check numeric refs ahead of the latest stable version before trusting them."""

        if self._tag_exists(usage.action_repository, usage.ref):
            return VersionResolution(usage, ref_kind, VersionStatus.CURRENT, catalog)
        if self._branch_exists(usage.action_repository, usage.ref):
            return VersionResolution(
                usage, RefKind.BRANCH, VersionStatus.FLOATING_BRANCH, catalog
            )
        return VersionResolution(
            usage, ref_kind, VersionStatus.INVALID_REF, catalog
        )

    def _tag_exists(self, action_repository: str, ref: str) -> bool:
        key = (action_repository.casefold(), ref)
        cached = self._tag_cache.get(key)
        if cached is not None:
            return cached

        repository = quote(action_repository, safe="/")
        tag = quote(ref, safe="")
        try:
            response = self._api.get_json(f"/repos/{repository}/git/ref/tags/{tag}")
        except GitHubNotFoundError:
            exists = False
        else:
            # GitHub may return prefix matches. Only an exact tag ref is valid.
            exists = (
                isinstance(response, dict)
                and response.get("ref") == f"refs/tags/{ref}"
            )
        self._tag_cache[key] = exists
        return exists

    def _branch_exists(self, action_repository: str, ref: str) -> bool:
        key = (action_repository.casefold(), ref)
        cached = self._branch_cache.get(key)
        if cached is not None:
            self._branch_cache_hits += 1
            return cached

        self._branch_lookups += 1
        repository = quote(action_repository, safe="/")
        branch = quote(ref, safe="")
        try:
            self._api.get_json(f"/repos/{repository}/branches/{branch}")
        except GitHubNotFoundError:
            exists = False
        else:
            exists = True
        self._branch_cache[key] = exists
        return exists


def _version_candidates(
    items: Iterable[Any], tag_field: str
) -> list[tuple[str, SemanticVersion]]:
    candidates: list[tuple[str, SemanticVersion]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if tag_field == "tag_name" and (
            item.get("draft", False) or item.get("prerelease", False)
        ):
            continue
        tag = item.get(tag_field)
        if not isinstance(tag, str):
            continue
        version = parse_semver(tag)
        if version is not None:
            candidates.append((tag, version))
    return candidates


def _unresolvable_resolution(
    usage: ActionUsage, catalog: ActionCatalogEntry
) -> VersionResolution:
    static = classify_static_ref(usage.ref)
    ref_kind = static[0] if static is not None else RefKind.ARBITRARY
    return VersionResolution(
        usage,
        ref_kind,
        VersionStatus.UNRESOLVABLE,
        catalog,
    )


def _compare_exact_version(
    current: SemanticVersion, latest: SemanticVersion
) -> VersionStatus:
    if current >= latest:
        return VersionStatus.CURRENT
    if current.major < latest.major:
        return VersionStatus.MAJOR_OUTDATED
    if current.minor < latest.minor:
        return VersionStatus.MINOR_OUTDATED
    return VersionStatus.PATCH_OUTDATED
