"""Regression checks that the public source release cannot publish real scan data."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PublicReleaseSafetyTests(unittest.TestCase):
    def test_generated_reports_are_not_git_tracked(self):
        if not (ROOT / ".git").exists() or shutil.which("git") is None:
            self.skipTest("requires a Git checkout")
        tracked = subprocess.run(
            ["git", "ls-files", "--", "reports/"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual("", tracked.stdout.strip())

    def test_reports_are_ignored_by_git(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("reports/", ignore.splitlines())
        self.assertIn(".env", ignore.splitlines())

    def test_only_unit_test_workflow_is_active(self):
        workflows = ROOT / ".github" / "workflows"
        active = sorted(p.name for p in workflows.iterdir() if p.suffix in (".yml", ".yaml"))
        self.assertEqual(["ci.yml"], active)
        ci = (workflows / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 -m unittest discover -s tests -v", ci)
        self.assertNotIn("scripts.audit", ci)
        self.assertNotIn("upload-artifact", ci)
        self.assertNotIn("secrets.", ci)
        self.assertNotIn("reports/", ci)

    def test_private_audit_is_only_an_inactive_example(self):
        example = ROOT / "examples" / "private-audit.yml"
        self.assertTrue(example.is_file())
        content = example.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch", content)
        self.assertNotIn("schedule:", content)
        self.assertNotIn("git push", content)
        self.assertNotIn("upload-artifact", content)


if __name__ == "__main__":
    unittest.main()
