# Kuulas Viewer (in progress)

A standalone native Mac reader/player for `.kuulas` project packages, with the
same view in Finder Quick Look. Kuulas stays the default editor. No NHSX export
or conversion is involved.

This directory currently contains reader groundwork, not a delivered app.
There is no tested installer or native playback yet. The first Swift reader
has not been compiled on a Mac; do not treat Python's passing tests as native
verification.

## Layout and tests

- `Sources/KuulasKit`: package snapshot reader. It opens only a private copy of
  `project.sqlite` and its WAL. SQLite must never open the original, even with
  `mode=ro`, which can create WAL/SHM sidecars.
- `Conformance/Session.kuulas`: generated synthetic project, not user data.
- `Conformance/expected.json`: expected heads and states from Python History.
- `Tools/make_conformance.py`: explicit fixture generator. Review its diff, never
  regenerate a golden file just to hide a native mismatch.
- `Tools/snapshot.py`: tested Python reference for no-source-write snapshotting.
- `Tests/KuulasKitTests`: native reader tests, intended for `swift test` on macOS.
- `tests/test_viewer_*.py` in the repository root: Python conformance and snapshot
  regressions, run with the normal Python test suite.

The fixture distinguishes current edit heads from abandoned newer nodes,
includes an alternative and archived edit, and exercises gates, auto-silence,
track automation, solo overriding mute, bus/master gain, pan, clip envelopes
and fades. Its media is linked relative to the package; its absolute source
path is deliberately nonexistent.

## Fidelity and safety gates

The current editor's VERSION/READER and schema are 4. Read `min_reader` from the
manifest; format introduction prose may describe older versions. Never open a
future reader requirement by ignoring unknown audible fields.

Snapshot copies are bounded (512 MiB DB+WAL, 64 MiB decompressed state). The source
must retain identity, size and times during the copy. SQLite validates/replays
the private WAL; do not use `immutable=1` on the live package. A changed source
must fail visibly rather than show a torn edit. Copy cost on large histories is
still a performance limit to measure, not an instant-preview claim.

Playback needs its own sample-level conformance against `kuulas.mixer`: the
NHSX planner's pan law, envelopes and media assumptions are not Kuulas's.
Unsupported audible state must prevent playback with an explanation. Displaying
a timeline successfully is not proof that its sound is faithful.

Open verification: macOS compile, actual pixels, native audio, live-WAL reader
cases in Swift, contained versus linked media in the Quick Look sandbox,
registration/type ownership and signed bundle checks. No release workflow or
editor packaging is changed in this groundwork.

`Conformance/audio.json` binds short stereo windows before/inside/after clip
fades, automation, gates and auto-silence to the real Python mixer. Run
`PYTHONPATH=src python viewer/Tools/make_audio_conformance.py` deliberately to
regenerate it. Golden comparison is exact on the Python side; the native player
must match within the recorded 1e-6 sample tolerance before playback is enabled.
