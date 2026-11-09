"""Data models shared by scanner and version resolver components."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


@dataclass(frozen=True, slots=True)
class RepositoryInfo:
    """Repository metadata needed to collect workflows."""

    full_name: str
    default_branch: str
    archived: bool
    fork: bool
    private: bool


@dataclass(frozen=True, slots=True)
class WorkflowFile:
    """A workflow fetched from a repository's default branch."""

    source_repository: str
    path: str
    content: str


@dataclass(frozen=True, slots=True)
class ActionUsage:
    """One external GitHub Action or reusable workflow reference."""

    source_repository: str
    workflow_path: str
    line_number: int
    raw: str
    action_repository: str
    subpath: str | None
    ref: str
    kind: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class CollectionWarning:
    """A recoverable workflow collection failure."""

    source_repository: str
    workflow_path: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Scanner output and basic collection counters."""

    usages: tuple[ActionUsage, ...]
    warnings: tuple[CollectionWarning, ...]
    repositories_scanned: int
    workflows_scanned: int


@dataclass(frozen=True, order=True, slots=True)
class SemanticVersion:
    """A normalized stable semantic version."""

    major: int
    minor: int
    patch: int


class RefKind(str, Enum):
    """Supported syntactic and GitHub-backed ref classifications."""

    MAJOR_TAG = "major"
    SEMVER = "semver"
    SHA = "sha"
    BRANCH = "branch"
    ARBITRARY = "arbitrary"


class VersionStatus(str, Enum):
    """Version status produced by the resolver."""

    INVALID_REF = "INVALID_REF"
    CURRENT = "CURRENT"
    PATCH_OUTDATED = "PATCH_OUTDATED"
    MINOR_OUTDATED = "MINOR_OUTDATED"
    MAJOR_OUTDATED = "MAJOR_OUTDATED"
    FLOATING_BRANCH = "FLOATING_BRANCH"
    SHA_PINNED = "SHA_PINNED"
    UNKNOWN_REF = "UNKNOWN_REF"
    UNRESOLVABLE = "UNRESOLVABLE"


@dataclass(frozen=True, slots=True)
class ActionCatalogEntry:
    """Latest stable upstream version for one unique Action repository."""

    action_repository: str
    latest_stable: str | None
    latest_version: SemanticVersion | None
    source: str | None
    repository_available: bool


@dataclass(frozen=True, slots=True)
class VersionResolution:
    """Resolver classification for one collected Action usage."""

    usage: ActionUsage
    ref_kind: RefKind
    status: VersionStatus
    catalog: ActionCatalogEntry


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    """Resolved usages plus recoverable upstream lookup failures."""

    resolutions: tuple[VersionResolution, ...]
    warnings: tuple[CollectionWarning, ...]


class AuditSeverity(str, Enum):
    """Human-oriented severity assigned to a version status."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class AuditFinding:
    """Normalized report row for one resolved Action usage."""

    source_repository: str
    workflow_path: str
    line_number: int
    action_repository: str
    subpath: str | None
    current_ref: str
    ref_kind: RefKind
    latest_stable: str | None
    status: VersionStatus
    severity: AuditSeverity

    def to_dict(self) -> dict[str, Any]:
        """Return the stable public JSON representation."""

        return {
            "source_repository": self.source_repository,
            "workflow": self.workflow_path,
            "line": self.line_number,
            "action": self.action_repository,
            "subpath": self.subpath,
            "current_ref": self.current_ref,
            "ref_type": self.ref_kind.value,
            "latest_stable": self.latest_stable,
            "status": self.status.value,
            "severity": self.severity.value,
        }


@dataclass(frozen=True, slots=True)
class AuditError:
    """Recoverable collection error retained in generated reports."""

    source_repository: str
    workflow_path: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Return the stable public JSON representation."""

        return {
            "source_repository": self.source_repository,
            "workflow": self.workflow_path,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class AuditSummary:
    """Deterministic counters shared by every report renderer."""

    repositories_scanned: int
    workflow_files_scanned: int
    action_usages: int
    unique_actions: int
    findings_by_severity: tuple[tuple[str, int], ...]
    findings_by_status: tuple[tuple[str, int], ...]
    errors: int

    def to_dict(self) -> dict[str, Any]:
        """Return counters with their normalized key order."""

        return {
            "repositories_scanned": self.repositories_scanned,
            "workflow_files_scanned": self.workflow_files_scanned,
            "action_usages": self.action_usages,
            "unique_actions": self.unique_actions,
            "findings_by_severity": dict(self.findings_by_severity),
            "findings_by_status": dict(self.findings_by_status),
            "errors": self.errors,
        }


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Normalized immutable input shared by Markdown and JSON renderers."""

    summary: AuditSummary
    findings: tuple[AuditFinding, ...]
    errors: tuple[AuditError, ...]
