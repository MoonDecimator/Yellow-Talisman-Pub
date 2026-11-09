"""Scanner MVP that joins collection and uses parsing."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Sequence

from .collector import RepositoryCollector, RepositoryFilter, WorkflowCollector
from .github_api import (
    DEFAULT_API_URL,
    GitHubApi,
    GitHubApiError,
    is_fatal_api_error,
)
from .models import CollectionWarning, RepositoryInfo, ScanResult
from .parser import parse_workflow


def scan(api: GitHubApi, policy: RepositoryFilter) -> ScanResult:
    """Collect workflows and return their external uses references."""

    repositories = RepositoryCollector(api).eligible_repositories(policy)
    return scan_repositories(api, repositories)


def scan_repositories(
    api: GitHubApi, repositories: Iterable[RepositoryInfo]
) -> ScanResult:
    """Scan a previously enumerated repository set without listing it again."""

    repository_list = tuple(repositories)
    workflow_collector = WorkflowCollector(api)
    usages = []
    warnings: list[CollectionWarning] = []
    workflows_scanned = 0

    for repository in repository_list:
        try:
            workflows, collection_warnings = workflow_collector.collect(repository)
        except GitHubApiError as error:
            if is_fatal_api_error(error):
                raise
            warnings.append(
                CollectionWarning(repository.full_name, None, str(error))
            )
            continue
        warnings.extend(collection_warnings)
        workflows_scanned += len(workflows)
        for workflow in workflows:
            usages.extend(parse_workflow(workflow))

    usages.sort(
        key=lambda usage: (
            usage.source_repository.casefold(),
            usage.workflow_path.casefold(),
            usage.line_number,
        )
    )
    return ScanResult(
        usages=tuple(usages),
        warnings=tuple(warnings),
        repositories_scanned=len(repository_list),
        workflows_scanned=workflows_scanned,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _argument_parser()
    arguments = parser.parse_args(argv)
    token = os.environ.get("WATCHTOWER_TOKEN")
    if not token:
        parser.error("WATCHTOWER_TOKEN is required")

    policy = RepositoryFilter(
        include_archived=arguments.include_archived,
        include_forks=arguments.include_forks,
        excluded_repositories=frozenset(arguments.exclude),
    )
    try:
        result = scan(GitHubApi(token, api_url=arguments.api_url), policy)
    except GitHubApiError as error:
        print(str(error), file=sys.stderr)
        return 1

    for usage in result.usages:
        print(json.dumps(usage.to_dict(), sort_keys=True))
    for warning in result.warnings:
        location = warning.source_repository
        if warning.workflow_path is not None:
            location = f"{location}:{warning.workflow_path}"
        print(f"warning: {location}: {warning.reason}", file=sys.stderr)
    print(
        "scanned "
        f"{result.repositories_scanned} repositories, "
        f"{result.workflows_scanned} workflows, "
        f"found {len(result.usages)} external uses references",
        file=sys.stderr,
    )
    return 0


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan GitHub Actions uses references")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--exclude", action="append", default=[], metavar="REPOSITORY")
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument("--include-forks", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
