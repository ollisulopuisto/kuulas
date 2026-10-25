# The cut list

Owner request 2026-10-23 (ROADMAP "Final Cut XML in and out"): hiding the cuts of one
speaker is the most useful thing a video rough cut can learn from kuulas, because a rough cut
that only hears loudness cannot know where the sound was cut. Code: `src/kuulas/cut_list.py`
(pure), `Session.cut_list`, `GET /api/cut-list`, File > Export cut list (JSON).

Read-only data about the edit. No recording is touched, and nothing here is written back
into the project.

## The file

```json
{"format": "kuulas-cut-list", "version": 1, "rate": 48000, "length": 336000,
 "media": [{"id": "m1", "name": "Anna.wav", "sha256": "...", "clock": "g1",
            "origin_flicks": 0}],
 "tracks": [{"id": "t1", "name": "Anna", "speaker": "Anna",
             "cuts": [{"at": 96000, "removed": 48000, "from": 96000, "to": 144000,
                       "clock": "g1"}]}],
 "seams": [{"at": 96000, "removed": 48000, "tracks": ["t1", "t2"]}]}
```

- **Frames** are samples at `rate` (the project rate). `length` is the end of the audible
  edit on the timeline.
- **cut**: a seam between two adjacent clips of a speech track where the recording clock
  jumps. `at` is where the second clip starts on the TIMELINE; `from` is where the first clip
  ended and `to` where the second starts, both on the RECORDING clock of the sync group
  `clock` (the same clock the sync group's other recordings are on, see `origin_flicks` in
  `media`); `removed = to - from` (negative when the edit goes back in the recording).
- A split that removes nothing, a gap between clips, and muting are not cuts. Music tracks
  are left out.
- **Unrelated recordings** side by side are a cut with `removed`, `from`, `to` and `clock`
  null (nothing says what was removed).
- **seams**: the timeline places where any track was cut, with the tracks that were. A ripple
  cut makes the same seam on every speech track; `removed` is null when the tracks disagree.
- **media**: the recordings the speech tracks play, with their checksum, so the other tool can
  match them to its own copies; `clock` is the sync group, `origin_flicks` the recording's
  start on that clock (1 flick = 1/705,600,000 s).

## Not in it (yet)

Who is heard when (gates, word times, speaker labels, overlaps): experience B in the
ROADMAP. The cover-shot rule that uses the list lives on the video side (autoraffkat).
