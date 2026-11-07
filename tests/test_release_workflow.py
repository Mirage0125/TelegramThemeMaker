from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


class ReleaseWorkflowTests(unittest.TestCase):
    def test_release_zip_excludes_user_assets(self):
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("--exclude='/assets/'", workflow)
        self.assertIn("if grep -q '^TelegramThemeMaker/assets/' release-file-list.txt", workflow)

    def test_release_zip_excludes_development_tests(self):
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("--exclude='/tests/'", workflow)

    def test_release_zip_excludes_local_dependency_overlays(self):
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("--exclude='.update-packages/'", workflow)
        self.assertIn("--exclude='.update-packages.rollback/'", workflow)
        self.assertIn("--exclude='.update-packages-stage-*/'", workflow)

    def test_release_zip_contains_bundled_default_cover(self):
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "cp assets/welcome.png dist/TelegramThemeMaker/defaults/welcome.png",
            workflow,
        )
        self.assertIn(
            "grep -qx 'TelegramThemeMaker/defaults/welcome.png' release-file-list.txt",
            workflow,
        )

    def test_regression_tests_run_before_release_build(self):
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertLess(
            workflow.index("      - name: Run regression tests"),
            workflow.index("      - name: Build ZIP and SHA-256"),
        )


if __name__ == "__main__":
    unittest.main()
