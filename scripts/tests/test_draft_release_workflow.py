"""Focused workflow guards. Run with Python + PyYAML, no macOS or side effects."""

import pathlib
import subprocess
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


def require(condition):
    if not condition:
        raise AssertionError("Workflow invariant failed")


class DraftReleaseTests(unittest.TestCase):
    def setUp(self):
        self.jobs = yaml.safe_load((ROOT / ".github/workflows/dmg.yml").read_text())[
            "jobs"
        ]
        self.draft = self.jobs["draft-release"]

    def test_exclusive_selection_and_arm64_runner(self):
        require("!(github.event_name" in self.jobs["dmg"]["if"])
        require("inputs.draft_release" in self.draft["if"])
        require(self.draft["runs-on"] == "macos-15")

    def test_no_storage_writes(self):
        for step in self.draft["steps"]:
            require("actions/cache" not in step.get("uses", ""))
            require("upload-artifact" not in step.get("uses", ""))
        uv = next(s for s in self.draft["steps"] if "setup-uv" in s.get("uses", ""))
        require(uv["with"]["enable-cache"] is False)
        require(uv["with"]["save-cache"] is False)
        require(
            self.draft["steps"][1]["with"]["ref"] == "${{ steps.source.outputs.sha }}"
        )

    def test_notarization_required_and_draft_target(self):
        runs = "\n".join(s.get("run", "") for s in self.draft["steps"])
        require('test -n "$APPLE_ID"' in runs)
        require('test -n "$APPLE_APP_PASSWORD"' in runs)
        require("--password" not in runs)
        require("--keychain-profile kuulas-ci-notary" in runs)
        require("shasum -a 256 -c SHA256.txt" in runs)
        require("stapler validate" in runs)
        require("--draft --prerelease" in runs)
        require('--target "$BUILD_SHA"' in runs)
        require("Current version has no changelog heading" in runs)

    def test_both_routes_keep_secrets_out_of_argv_and_checksums_portable(self):
        for job in self.jobs.values():
            runs = "\n".join(s.get("run", "") for s in job["steps"])
            require('--password "$APPLE_APP_PASSWORD"' not in runs)
            require('-p "$KEYCHAIN_PASSWORD"' not in runs)
            require('-P "$P12_PASSWORD"' not in runs)
            require("macos_ci_credentials.py import-certificate" in runs)
            require("macos_ci_credentials.py store-notary-credentials" in runs)
            require("shasum -a 256 -c SHA256.txt" in runs)

    def test_shell_syntax(self):
        for step in self.draft["steps"]:
            if "run" in step:
                subprocess.run(
                    ["/bin/bash", "-n"], input=step["run"], text=True, check=True
                )


if __name__ == "__main__":
    unittest.main()
