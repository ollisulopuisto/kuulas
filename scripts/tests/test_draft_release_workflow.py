"""Focused workflow guards. Run with Python + PyYAML, no macOS or side effects."""

import pathlib
import subprocess
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


class DraftReleaseTests(unittest.TestCase):
    def setUp(self):
        self.jobs = yaml.safe_load((ROOT / ".github/workflows/dmg.yml").read_text())[
            "jobs"
        ]
        self.draft = self.jobs["draft-release"]

    def test_exclusive_selection_and_arm64_runner(self):
        assert "!(github.event_name" in self.jobs["dmg"]["if"]
        assert "inputs.draft_release" in self.draft["if"]
        assert self.draft["runs-on"] == "macos-15"

    def test_no_storage_writes(self):
        for step in self.draft["steps"]:
            assert "actions/cache" not in step.get("uses", "")
            assert "upload-artifact" not in step.get("uses", "")
        assert self.draft["steps"][1]["with"]["ref"] == "${{ steps.source.outputs.sha }}"

    def test_notarization_required_and_draft_target(self):
        runs = "\n".join(s.get("run", "") for s in self.draft["steps"])
        assert 'test -n "$APPLE_ID"' in runs
        assert 'test -n "$APPLE_APP_PASSWORD"' in runs
        assert "stapler validate" in runs
        assert "--draft --prerelease" in runs
        assert '--target "$BUILD_SHA"' in runs
        assert "Current version has no changelog heading" in runs

    def test_shell_syntax(self):
        for step in self.draft["steps"]:
            if "run" in step:
                subprocess.run(
                    ["/bin/bash", "-n"], input=step["run"], text=True, check=True
                )


if __name__ == "__main__":
    unittest.main()
