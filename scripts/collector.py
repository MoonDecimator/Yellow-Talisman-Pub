"""Repository filtering and workflow collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote

from .github_api import (
    GitHubApi,
    GitHubApiError,
    GitHubNotFoundError,
    is_fatal_api_error,
)
from .models import CollectionWarning, RepositoryInfo, WorkflowFile


@dataclass(frozen=True, slots=True)
class RepositoryFilter:
    """Selection policy for installation repositories."""

    include_archived: bool = False
    include_forks: bool = False
    included_repositories: frozenset[str] = field(default_factory=frozenset)
    excluded_repositories: frozenset[str] = field(default_factory=frozenset)

    def includes(self, repository: RepositoryInfo) -> bool:
        short_name = repository.full_name.rsplit("/", 1)[-1]
        candidates = {repository.full_name.casefold(), short_name.casefold()}
        included = {name.casefold() for name in self.included_repositories}
        if included and candidates.isdisjoint(included):
            return False
        if repository.full_name in self.excluded_repositories:
            return False
        if short_name in self.excluded_repositories:
            return False
        if repository.archived and not self.include_archived:
            return False
        if repository.fork and not self.include_forks:
            return False
        return True


class RepositoryCollector:
    """Enumerate repositories visible to the current App installation."""

    def __init__(self, api: GitHubApi) -> None:
        self._api = api

    def list_repositories(self) -> tuple[RepositoryInfo, ...]:
        repositories = (
            RepositoryInfo(
                full_name=item["full_name"],
                default_branch=item["default_branch"],
                archived=bool(item.get("archived", False)),
                fork=bool(item.get("fork", False)),
                private=bool(item.get("private", False)),
            )
            for item in self._api.get_paginated(
                "/installation/repositories", item_key="repositories"
            )
        )
        return tuple(sorted(repositories, key=lambda repo: repo.full_name.casefold()))

    def eligible_repositories(
        self, policy: RepositoryFilter
    ) -> tuple[RepositoryInfo, ...]:
        return tuple(repo for repo in self.list_repositories() if policy.includes(repo))


class WorkflowCollector:
    """List and fetch workflow files from a repository's default branch."""

    def __init__(self, api: GitHubApi) -> None:
        self._api = api

    def list_workflow_paths(self, repository: RepositoryInfo) -> tuple[str, ...]:
        endpoint = f"/repos/{_repository_path(repository)}/contents/.github/workflows"
        try:
            entries = self._api.get_json(
                endpoint, params={"ref": repository.default_branch}
            )
        except GitHubNotFoundError:
            return ()
        if not isinstance(entries, list):
            raise TypeError("Workflow directory response must be a list.")
        paths = (
            entry["path"]
            for entry in entries
            if entry.get("type") == "file"
            and str(entry.get("path", "")).lower().endswith((".yml", ".yaml"))
        )
        return tuple(sorted(paths, key=str.casefold))

    def fetch_workflow(
        self, repository: RepositoryInfo, workflow_path: str
    ) -> WorkflowFile | None:
        encoded_path = quote(workflow_path, safe="/")
        endpoint = f"/repos/{_repository_path(repository)}/contents/{encoded_path}"
        try:
            content = self._api.get_text(
                endpoint, params={"ref": repository.default_branch}
            )
        except GitHubNotFoundError:
            return None
        return WorkflowFile(repository.full_name, workflow_path, content)

    def collect(
        self, repository: RepositoryInfo
    ) -> tuple[tuple[WorkflowFile, ...], tuple[CollectionWarning, ...]]:
        workflows: list[WorkflowFile] = []
        warnings: list[CollectionWarning] = []
        for path in self.list_workflow_paths(repository):
            try:
                workflow = self.fetch_workflow(repository, path)
            except GitHubApiError as error:
                if is_fatal_api_error(error):
                    raise
                warnings.append(
                    CollectionWarning(repository.full_name, path, str(error))
                )
                continue
            if workflow is None:
                warnings.append(
                    CollectionWarning(
                        repository.full_name,
                        path,
                        "workflow disappeared before it could be fetched",
                    )
                )
                continue
            workflows.append(workflow)
        return tuple(workflows), tuple(warnings)


def _repository_path(repository: RepositoryInfo) -> str:
    return quote(repository.full_name, safe="/")
