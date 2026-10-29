# Kuulas Viewer, 29 October 2026

Owner: Kuulas Viewer lane. In progress on `feat/kuulas-viewer` from `92607191`.

The target is a standalone native Mac read-only `.kuulas` viewer, with timeline,
play/pause/seek and the same view in Finder Quick Look. This is not an NHSX
conversion and not the older metadata-only WP61 scope. Kuulas remains the default
editor for its existing `fi.sulopuisto.kuulas.project` package type.

## Boundaries

- New viewer code, its conformance fixtures/tests and this handoff only initially.
- No changes to history, backups, range restore, recording meters, current editor
  packaging, release versions, or existing NHSX Viewer source.
- NHSX Viewer release owner has no active implementation branch or Kuulas file
  claims. Its released source is `d10601ef` in podcast, tag
  `viewer-v2026.10.29.1`; completion docs PR138 is independent.
- Read the manifest and a consistent SQLite read transaction, including live WAL.
  Never start a Session, migrate, acquire project locks, save resume state or use
  SQLite `immutable=1` on an actively edited project.
- Resolve the selected edit explicitly; do not assume latest history node means
  the current head. Include archived/alternative edits in reader tests.
- Prove native interpretation against fixtures made through the current Python
  model/history code. Unsupported audible features must disable playback with
  a visible reason, not silently change the mix.

## Verification still required

Native app/Quick Look builds and installation, sandbox access to contained versus
linked media, live-WAL read-only behavior, native audio and actual visual layout.
No app or installer has been delivered yet. No approximation is accepted merely
because a parser returns data.

## Reader groundwork, 11:30 Helsinki

- Current source has format VERSION/READER 4, schema 4. The FORMAT introduction's
  v1 label is stale. Gates require min_reader3, clip auto-silence min_reader4.
- Direct History(read_only=True) on a closed fixture creates WAL/SHM sidecars.
  The viewer must read a private DB+WAL copy instead. A Python reference experiment
  checks source identity/size/mtime/ctime around copying, opens only the private
  copy, includes committed live WAL and rejects a source changed during copying.
- A generated synthetic fixture binds all edit heads (including undone newer
  nodes, an alternative and an archived edit), compressed states, bus/master,
  solo/mute, clip automation/fades, gates/auto-silence and a moved linked file.
  Python History verifies its expected states. This is groundwork, not native
  playback parity or a built app.

Native reader code and SwiftPM tests are drafted but NOT compiled. Portable
verification expanded to 61 passing tests (viewer, History and package), with
Ruff clean for new Python code. The native playback eligibility gate refuses
all audio until sample-level conformance exists; complex fixture reasons are
explicit. No host app or Quick Look extension exists yet.

Native integration requires a separately approved workflow patch. The smallest
first step is one macOS SwiftPM test job, scoped to changes under viewer/ and its
Python fixture tests, with timeout/concurrency cancellation; no artifact upload,
release, editor bundle build or dispatch. Source PR approval is not approval to
push workflow changes or spend runner time.

Audio groundwork now has Python mixer-generated stereo sample windows around
clip boundaries, automation, gate and auto-silence transitions, including all
three edits. A fifth regression re-evaluates those windows against the current
mixer. This does not yet prove any native player.
