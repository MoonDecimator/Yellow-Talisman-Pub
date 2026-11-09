from pathlib import Path
import unittest

from scripts.models import WorkflowFile
from scripts.parser import parse_workflow


FIXTURES = Path(__file__).parent / "fixtures"


class ParserTests(unittest.TestCase):
    def test_ignores_uses_inside_literal_and_folded_block_scalars(self):
        workflow = WorkflowFile(
            "org/source",
            ".github/workflows/block-scalars.yml",
            """jobs:
  example:
    steps:
      - run: |
          echo test
          uses: fake/literal@v1
      - run: >-
          echo folded
          uses: fake/folded@v2
      - uses: actions/checkout@v4
""",
        )

        usages = parse_workflow(workflow)

        self.assertEqual(1, len(usages))
        self.assertEqual("actions/checkout", usages[0].action_repository)
        self.assertEqual(10, usages[0].line_number)

    def test_excludes_local_parent_relative_and_docker_references(self):
        workflow = WorkflowFile(
            "org/source",
            ".github/workflows/excluded.yml",
            """steps:
  - uses: ./local-action
  - uses: ../shared-action
  - uses: docker://alpine:latest
""",
        )

        self.assertEqual((), parse_workflow(workflow))

    def test_mixed_workflow_extracts_external_references(self):
        workflow = WorkflowFile(
            source_repository="org/source",
            path=".github/workflows/mixed.yml",
            content=(FIXTURES / "workflow_mixed.yml").read_text(),
        )

        usages = parse_workflow(workflow)

        self.assertEqual(4, len(usages))
        self.assertEqual(
            [5, 6, 7, 12], [usage.line_number for usage in usages]
        )
        self.assertEqual("actions/checkout", usages[0].action_repository)
        self.assertEqual("v4", usages[0].ref)
        self.assertEqual("actions/setup-python", usages[1].action_repository)
        self.assertEqual("owner/action", usages[2].action_repository)
        self.assertEqual("path/to/action", usages[2].subpath)
        self.assertEqual("reusable_workflow", usages[3].kind)
        self.assertEqual(".github/workflows/build.yml", usages[3].subpath)

    def test_rejects_malformed_references(self):
        workflow = WorkflowFile(
            "org/source",
            ".github/workflows/bad.yml",
            """steps:
  - uses: missing-ref
  - uses: owner-only@v1
  - uses: owner/repo@ref with spaces
  - uses: 'owner/repo@v1' trailing
  - notuses: actions/checkout@v4
""",
        )

        self.assertEqual((), parse_workflow(workflow))

    def test_preserves_raw_reference_and_source_fields(self):
        workflow = WorkflowFile(
            "org/source", ".github/workflows/ci.yml", "- uses: owner/repo@abc123\n"
        )

        usage = parse_workflow(workflow)[0]

        self.assertEqual("org/source", usage.source_repository)
        self.assertEqual(".github/workflows/ci.yml", usage.workflow_path)
        self.assertEqual("owner/repo@abc123", usage.raw)
        self.assertIsNone(usage.subpath)


if __name__ == "__main__":
    unittest.main()
