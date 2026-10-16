# WP13 Hindenburg Session Import

`import_nhsx` parses sessions with `nhsx.read`, uses `nhsx.pipeline.tracks` to
locate usable audio files, and uses `nhsx.mix.plan` for the source fade ramps.
It imports media and creates named tracks and clips in one history step.
Region start, source offset, length, gain, pan, mute, and simple fades are
mapped to frames and clip fields. Raised-cosine source ramps are sampled into
the source-clock envelope. File transcription words remain on each recording
clock and preserve speaker labels.

Missing or unreadable audio is reported per file; good files and regions still
import. The original session XML and the original file, track, and region XML
are kept under the matching objects' `extra["nhsx"]` for a future exporter.
This work does not add Hindenburg export.

## Verification

- Tests were added first and failed because `import_nhsx` was not registered.
- Real `h-test A.nhsx` fixture with generated audio, source-clock word test,
  invalid XML, missing audio, and corrupt audio: 5 focused tests pass.
- Full suite: 412 passed with one existing Starlette deprecation warning.
- Ruff: clean.

Release version, changelog, and WP status edits are left for branch integration
under the worktree handoff rules.
