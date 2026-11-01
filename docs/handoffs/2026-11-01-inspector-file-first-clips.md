# Inspector clip list: file-first grouping (2026-11-01)

User ask (voice): the track Inspector's clip list showed one row per clip, so a
track cut from a few recordings repeated the same file name for every clip.
The list is now file-first: one expandable row per source file, clips of that
file underneath.

## Behaviour

- Section renamed file-first: "Files on this track" / "Raidan tiedostot".
- `trackFileRows(project, trackId)` groups the track's clips by media id, in
  the timeline order of each file's first clip. Files that share a name stay
  separate rows (identity is the media id, not the name); a clip without media
  is its own file row.
- Each file row is a native `<details>`: summary shows the file name and clip
  count (`ui.inspector.clips.count`, en/fi plural forms). Clips underneath keep
  the existing rows: timeline order, timing and muted state, click jumps the
  play cursor and selects, `aria-pressed` follows the selection.
- Open state survives rebuilds per file; a file holding the current selection
  opens on its own. Empty track keeps the "no clips" hint.
- Styling reuses `.inspector-track-clips` tokens; new rules only indent the
  nested list and style the file summary (no colour literals).

## Verification

- TDD: red tests first in `ui/tests/inspector.test.js` (grouping, same-name
  files stay separate, jump/selection preserved, empty state), then the
  implementation. Suite: 3661 pass. `biome check ui/` clean; i18n parity
  passes.
- Pixel proof: Playwright-rendered harness of the real module and stylesheet
  (repeated file name collapses to one row per file; selected clip's file
  auto-opens). Not verified in the packaged native app.

## Not in scope

- No flat/file view toggle: the grouped list is the only view, per the ask's
  "file-first default" reading. Add a toggle only if the user asks.
