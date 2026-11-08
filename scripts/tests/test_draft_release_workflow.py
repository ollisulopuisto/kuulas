"""Focused workflow guards. Run with Python + PyYAML, no macOS or side effects."""
import pathlib
import subprocess
import unittest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]

class DraftReleaseTests(unittest.TestCase):
    def setUp(self):
        self.jobs = yaml.safe_load((ROOT / '.github/workflows/dmg.yml').read_text())['jobs']
        self.draft = self.jobs['draft-release']

    def test_exclusive_selection_and_arm64_runner(self):
        self.assertIn('!(github.event_name', self.jobs['dmg']['if'])
        self.assertIn('inputs.draft_release', self.draft['if'])
        self.assertEqual(self.draft['runs-on'], 'macos-15')

    def test_no_storage_writes(self):
        for step in self.draft['steps']:
            self.assertNotIn('actions/cache', step.get('uses', ''))
            self.assertNotIn('upload-artifact', step.get('uses', ''))
        self.assertEqual(self.draft['steps'][1]['with']['ref'], '${{ steps.source.outputs.sha }}')

    def test_notarization_required_and_draft_target(self):
        runs = '\n'.join(s.get('run', '') for s in self.draft['steps'])
        self.assertIn('test -n "$APPLE_ID"', runs)
        self.assertIn('test -n "$APPLE_APP_PASSWORD"', runs)
        self.assertIn('stapler validate', runs)
        self.assertIn('--draft --prerelease', runs)
        self.assertIn('--target "$BUILD_SHA"', runs)
        self.assertIn('Current version has no changelog heading', runs)

    def test_shell_syntax(self):
        for step in self.draft['steps']:
            if 'run' in step:
                subprocess.run(['bash', '-n'], input=step['run'], text=True, check=True)

if __name__ == '__main__':
    unittest.main()
