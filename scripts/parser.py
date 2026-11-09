"""Line-oriented parser for uses references in GitHub Actions workflows."""

from __future__ import annotations

import re

from .models import ActionUsage, WorkflowFile


USES_LINE = re.compile(r"^\s*(?:-\s*)?uses\s*:\s*(?P<value>.*?)\s*$")
REPOSITORY_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")
BLOCK_SCALAR_HEADER = re.compile(
    r"^(?P<indent> *)(?:-\s*)?[A-Za-z0-9_.-]+\s*:\s*"
    r"[|>](?:[1-9][+-]?|[+-][1-9]?|[+-])?$"
)


def parse_workflow(workflow: WorkflowFile) -> tuple[ActionUsage, ...]:
    """Extract external uses references while retaining source line numbers."""

    usages: list[ActionUsage] = []
    block_scalar_indent: int | None = None
    for line_number, line in enumerate(workflow.content.splitlines(), start=1):
        if block_scalar_indent is not None:
            if not line.strip() or _indentation(line) > block_scalar_indent:
                continue
            block_scalar_indent = None

        scalar_indent = _block_scalar_indent(line)
        if scalar_indent is not None:
            block_scalar_indent = scalar_indent
            continue

        value = _uses_value(line)
        if value is None or value.startswith(("./", "../")):
            continue
        if value.lower().startswith("docker://"):
            continue
        usage = _parse_external_reference(workflow, line_number, value)
        if usage is not None:
            usages.append(usage)
    return tuple(usages)


def _block_scalar_indent(line: str) -> int | None:
    header = line.split("#", 1)[0].rstrip()
    match = BLOCK_SCALAR_HEADER.match(header)
    return len(match.group("indent")) if match is not None else None


def _indentation(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _uses_value(line: str) -> str | None:
    match = USES_LINE.match(line)
    if match is None:
        return None
    candidate = match.group("value").strip()
    if not candidate:
        return None
    if candidate[0] in ("'", '"'):
        quote = candidate[0]
        closing = candidate.find(quote, 1)
        if closing == -1:
            return None
        remainder = candidate[closing + 1 :].strip()
        if remainder and not remainder.startswith("#"):
            return None
        return candidate[1:closing].strip()
    value = candidate.split("#", 1)[0].strip()
    return value if value and not any(character.isspace() for character in value) else None


def _parse_external_reference(
    workflow: WorkflowFile, line_number: int, value: str
) -> ActionUsage | None:
    location, separator, ref = value.rpartition("@")
    if not separator or not location or not ref or any(char.isspace() for char in ref):
        return None
    components = location.split("/")
    if len(components) < 2 or not all(components[:2]):
        return None
    if not all(REPOSITORY_COMPONENT.fullmatch(part) for part in components[:2]):
        return None
    action_repository = "/".join(components[:2])
    subpath = "/".join(components[2:]) or None
    if subpath is not None and any(part in ("", ".", "..") for part in components[2:]):
        return None
    kind = (
        "reusable_workflow"
        if subpath is not None
        and subpath.startswith(".github/workflows/")
        and subpath.lower().endswith((".yml", ".yaml"))
        else "github_action"
    )
    return ActionUsage(
        source_repository=workflow.source_repository,
        workflow_path=workflow.path,
        line_number=line_number,
        raw=value,
        action_repository=action_repository,
        subpath=subpath,
        ref=ref,
        kind=kind,
    )
