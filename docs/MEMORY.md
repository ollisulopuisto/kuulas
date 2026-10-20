# Memory: O(window), never O(duration)

Owner rule (2026-10-20): a 5-track, 1.5-hour session must open, play, edit,
show waveforms and run Auto-Silence, loudness, automix and export without
running the Mac out of memory. Memory grows with the window being worked on,
never with the length of the programme. No whole-file audio in RAM.

## The incident

The owner's MacBook (24 GB) was running v26.10.20.2 on a 47-minute, 5-track
project. It went into a swap storm, the WindowServer watchdog fired (main
thread unresponsive for 40 s), and the Mac had to be forced off.

macOS reported at 12:08 Helsinki:

| Process | Memory |
|---|---|
| WindowServer | 5.0 GB (normally under 1 GB) |
| Kuulas, three processes | 3.0 GB, 1.8 GB, 1.6 GB |
| Helium renderers, two | 2.2 GB, 1.9 GB |

Compressor was full.

### The cause

Every audio read went through `MediaStore._chunk`, which keeps each decoded
10 s chunk in the shared cache budget (`memory.BUDGET`, 2 GB, LRU).

- **In the editor:** playback read-ahead goes through the store, so over a
  long session the cache filled up to its 2 GB cap. On top of that come the
  engine's own read-ahead, the pyramids, the history and the Python heap.
  Hence the 3 GB.
- **In each analysis worker:** one scan of the project (loudness curves,
  Auto-Silence) filled the worker's own 2 GB budget. Hence the 1.8 and
  1.6 GB.

In v26.10.20.2 there could be up to ~35 such workers at once. That was fixed
in v26.10.20.4, but each worker could still reach ~2.5 GB.

## Measured: before and after

`scripts/memory_bench.py` runs each path in a fresh Python process (which is
what an analysis worker is) on 5 mono 48 kHz noise tracks of 47 minutes, with
speakers taking turns. It reports peak RSS (`ru_maxrss`). Caches are deleted
first, so every run is cold. Measured on the Mac Studio (M1 Max, 32 GB) on
2026-10-20.

Peak RSS per process, in GiB. The process starts at 0.11.

| Path | v26.10.20.4 | this branch |
|---|---|---|
| Waveform peaks / pyramid of all 5 files | 2.38 | 0.20 |
| Speech lanes (track_levels, automix input) | 2.52 | 0.43 |
| Auto-Silence (silence_ranges) | 2.50 | 0.42 |
| Automix ducking | 2.53 | 0.45 |
| Loudness curves (project_curves, 5 tracks + mix) | 2.68 | 0.53 |
| Export mix (WAV) | 3.35 | 0.84 |
| Export all tracks | 3.17 | 0.44 |
| Import of the 5 files | 0.22 | 0.22 (unchanged: streams already) |

### Mastered export

Mastered export still holds the whole programme. speechmix's
`programme.master` works on the whole stereo programme in float64 and keeps
several per-sample curves.

| Length | Peak RSS (stereo master) |
|---|---|
| 5 min | 2.40 GiB |
| 10 min | 2.91 GiB |
| 20 min | 5.12 GiB |

That is about 38 B per sample per channel on top of a ~0.6 GB render, which
extrapolates to:

| Length | Estimated peak |
|---|---|
| 47 min | ~11 GB |
| 90 min | ~21 GB |

This is now refused before it starts (see below).

## Acceptance

`tests/manual/test_memory_acceptance.py` (marker `slow`) is run by hand. It
uses 5 stereo, 24-bit, 48 kHz tracks, and one editor process (a fresh Python)
does the following:

1. Import.
2. Build the peaks.
3. Run playback read-ahead through the whole programme (the engine's helper,
   no device, faster than real time).
4. Compute the loudness curves and Auto-Silence in the real analysis worker.
5. Export the mix.

Asserted:

- Editor peak at most 2.5 GiB.
- Worker peak at most 600 MiB.
- The editor's peak grows by less than 100 KB per second of programme. The
  audio itself would be 1.9 MB/s.

| Length | Editor peak | Worker peak | Chunk cache at end |
|---|---|---|---|
| 10 min | 1.19 GiB | 0.37 GiB | 0 |
| 30 min | 1.29 GiB | 0.42 GiB | 0 |
| 90 min | 1.23 GiB | 0.58 GiB | 0 |

That run was before the worker's 2-tracks-at-once cap and its 64 MB budget.
A re-run with both was still going at hand-back.

Before the engine fix below, the same run reached 1.68 GiB at 10 min and
2.77 GiB at 30 min in the read-ahead stage alone.

The always-on version is in `tests/test_memory_ceiling.py`. It runs the
paths on 1-minute and 4-minute projects and asserts that the Python heap
peak (`tracemalloc`) grows by less than 12 000 B per second of audio. The
audio itself is 64 000 B/s at the test's 16 kHz.

## What changed

- **`memory.MemoryBudget` caps namespaces.** `chunks` (decoded audio) may
  hold at most 192 MB of the 2 GB budget (`NAMESPACE_LIMITS`). The
  performance report lists what each namespace holds.
- **`media.streaming()`.** Reads inside it come straight from the file and
  are not cached. It is used by every scan from start to end:
  - peaks;
  - level envelopes;
  - `analysis._from_audio`;
  - loudness curves and speech levels;
  - export rendering;
  - the engine's read-ahead, which is its own cache, so the store's copy was
    a duplicate.

  The analysis worker streams every read (`media.STREAM_ALL`) and has a
  64 MB budget.
- **The worker measures at most 2 tracks at once**
  (`analysis.MAX_TRACKS_AT_ONCE`, set through `KUULAS_TRACKS_AT_ONCE`). Each
  track measurement holds its file's level envelope and a cumulative sum of
  it. With all 5 at once, the worker reached 0.58 GiB on 90 minutes.
- **The engine's read-ahead keeps at most `MAX_SPARE_CHUNKS` (64) unwanted
  chunks.** It used to keep everything decoded in the last 3 s of wall time.
  A playhead moving faster than real time (shuttle, seeks) grew it without
  bound.
- **Loudness curves read 15 s per step instead of 60.** The meter keeps its
  state, so the curve is the same; there is a golden test against 60 s.
- **Export renders 10 s blocks instead of 30.** Up to 2 × workers blocks
  are in flight.
- **The worker has a hard ceiling.** `rss.Ceiling` reads the worker's own
  RSS at every `priority.checkpoint`; on macOS that is one `task_info` call,
  with no `ps`. Above `KUULAS_WORKER_MAX_MB` (default 1536) the worker stops
  with `error.offload.memory`. The editor shows that error, and the task
  backs off like a failed worker (5 s, 10 s … 300 s), so there is no retry
  storm. `setrlimit(RLIMIT_AS)` is not used: macOS does not enforce it, and it
  counts address space, not memory.
- **The worker reports its peak RSS** (`peak_rss` in every answer). The
  editor logs it and keeps the last and largest (`offload.WORKER_PEAKS`). The
  performance report shows them.
- **The editor watches its own RSS** (`memory.start_rss_watch`, every 30 s).
  It logs `log.memory.high` above 3 GB, and again for each further 512 MB.
- **Mastering is refused** when `40 B × samples × channels` would exceed half
  of the computer's RAM (`export.master_fits`). The message is
  `error.export.master_memory`, which says to export without mastering or to
  master a shorter selection. On 24 GB that allows about 55 minutes of
  stereo.
- **UI canvases are capped at 8 Mpx each** (`ui/canvas-size.js`): the
  timeline overlay, the waveform layer (worker and main thread) and the
  overview. See the UI section below.

## Audit: what still grows with duration

Estimated for 5 tracks × 5400 s × 48 kHz stereo, worst first.

| Path | Holds | Size at 90 min | Status |
|---|---|---|---|
| Mastered export (`export._mastered` → speechmix `programme.master`) | whole programme float64 + ~6 per-sample curves | ~21 GB | **Refused** above 50 % of RAM. Real fix: a streaming master in speechmix (podcast repo, ground rule 7). |
| Automix run (`automix.run` → `podcast/apps/automixer` child) | `sf.read` of whole stems, float64 (`domain/track.py:194`) | 10–20 GB in the child | **Open**: the automixer's own code. No ceiling yet. |
| Local transcription (faster-whisper in `transcribe_worker`) | one file decoded to 16 kHz float32 | ~0.9 GB per file, one at a time | Acceptable; own process. |
| Onsets (`onsets.detect_from_peaks`) | ~10 per-millisecond arrays | ~0.4 GB transient per file | Open, low priority. Window it later. |
| Level envelopes (`levels.block_energy`) | one float64 per 60 frames, per file | 35 MB per track, 173 MB in total | Acceptable: 1/60 of the audio, disk-backed (`caches/analysis/*.npy`). `energy_upto` rebuilds a whole-file cumsum per clip (~70 MB transient). |
| Peak pyramid | min/max per 256 frames | 8 MB per track | Disk-backed (`caches/peaks/*.npz`), loaded through the budget. |
| Per-hop arrays (lanes, gates, `bleed_relative`) | 20 ms hops | ~3 MB per track | Acceptable. |

Checked and bounded:

- `mixer.mix` / `track_stem`
- `loudness.measure_clip`
- `clipboard_level`
- `send_copy`
- import (`_link` / `_encode_*`)
- the engine read-ahead
- `stretch`
- `project_stats`, `speech_stats`, `music_report`

`ab_match.match_gains` copies its input to float64, but nothing calls it.

## UI: WindowServer and GPU memory

What was checked:

- **Canvas sizes.** Every canvas is the size of its viewport (the
  `.timeline-stack` box, `overflow: hidden`), never the timeline's length. The
  backing size is set only on resize (`ResizeObserver`), not per frame.
- **The playhead redraw.** It redraws the overlay every animation frame while
  playing (v26.10.20.2, `drawOverlay` from `playhead-clock.js`). It draws on
  the one existing canvas: no canvas, `ImageBitmap`, `Path2D` cache or pattern
  is created per frame.
- **The waveform worker.** It draws on one transferred `OffscreenCanvas`.
- **The peak-tile caches.** They are capped at 600 tiles × 8 KB, both in the
  worker and in the main thread's ghost tiles.
- **Images and URLs.** There are no `ImageBitmap` caches. The
  `createObjectURL` calls are one per download.

What was found:

- **No growing canvases and no leaked layers.**
- **The one unbounded factor was resolution.** A full-screen timeline at
  device ratio 2 on a 5K display is 14.7 Mpx = 59 MB per canvas, three
  canvases, and the window server keeps its own surfaces of each. That cost
  is now capped at 8 Mpx per canvas by lowering the ratio slightly (node
  tests in `ui/tests/canvas-size.test.js`).

The WindowServer's 5 GB is more likely the swap storm itself (its surfaces
paged out and back while memory ran out) than a UI leak. This is not
verified: it needs a long playback session watched in Activity Monitor
(roadmap).

## How to measure

```
uv run python scripts/memory_bench.py --minutes 47 --tracks 5
KUULAS_MEMORY_MINUTES=10,30,90 uv run pytest -q -s tests/manual/test_memory_acceptance.py
```

In the app, Help > Record a performance report shows:

- the editor's RSS now and at its peak;
- the analysis worker's last and largest peak;
- what each cache namespace holds.
