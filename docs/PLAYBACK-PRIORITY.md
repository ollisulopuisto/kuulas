# Playback priority

Owner rule (2026-10-20): background processing must never compete with
playback. Only the recorder (`kuulas_recorder`, its own process) outranks it.

Why: the editor has one GIL. A `sample` of the app during choppy playback
showed two worker threads busy in scipy `resample_poly`, numpy, numba and
libsndfile reads, while the PortAudio callback waited about 130 samples for
the GIL. `resample_poly` is the true-peak meter in `loudness_curve`, which the
UI asks for on its own after edits. The rest is the speech-level analysis in
`analysis.py`.

## The mechanism

- **`priority.GATE`** (`src/kuulas/priority.py`) knows whether audio plays. It
  reads `Engine.is_playing`, a plain attribute. It never takes `_tlock`, so
  polling it never contends with the audio callback. It holds for 1 s after
  playback stops, after a scrub, and after any input while playing.
  `server.create_app` connects it to the engine. The HTTP middleware feeds it
  input.
- **Background threads are marked.** That covers `Jobs` workers,
  `priority.background()`, `priority.executor`, `priority.gated_map` and
  `priority.thread`. Their pool threads inherit the mark, the job's cancel
  event and its pause listener.
- **`priority.checkpoint()`** runs between chunks of every heavy loop. On a
  marked thread it waits while the gate says playing. On a request thread the
  UI waits on, it only checks cancel, because pausing there could hold the
  session lock.
- **`priority.gated_map`** replaces thread pools:
  - A background caller starts no new item while audio plays.
  - At most one item runs while the user is interacting (playing, or input in
    the last 2 s).
- **Jobs** start nothing while audio plays. A running job pauses at its next
  progress call or checkpoint and stays listed as running, with
  `paused: true` and the message `job.paused_playing` ("Paused while playing").
  The ETA is blank while paused, and paused time does not count towards it.
  The job resumes where it was, and cancel works while paused.
- **Low QoS.** Marked threads ask for utility QoS on macOS (nice +10 on
  Linux). Not background QoS: a background-QoS thread that holds the GIL on an
  efficiency core would make the callback wait longer.
- **Analysis worker process** (`offload.py`, `analysis_worker.py`): heavy
  analysis runs in `python -m kuulas.analysis_worker`, which has its own GIL:
  - It takes nice 19 first. After its imports it enters the Darwin background
    band. Imports in the band took 4.7 s instead of 0.7 s under load.
  - When the caller is background work, the editor stops the worker with
    SIGSTOP while audio plays and continues it afterwards. Cancel kills it.
  - It writes the same content-keyed caches the editor reads.
  - Fail soft: a store it cannot reopen, or a worker that does not answer, is
    measured in the editor under the gate, with a log line.
  - The bundle runs it via `bundle.worker_module` / `_run_analysis_worker`.
    Its log is `kuulas-analysis.log`.
  - `--selftest` checks that it starts at nice 19.
- **Guard.** `tests/test_thread_guard.py` fails on any new raw `Thread` or
  `ThreadPoolExecutor` under `src/kuulas` (the engine is not scanned). The fix
  is to route it through `priority` or to list it with a reason.

## Background compute paths

| Path | Where | Now |
|---|---|---|
| Auto-Silence (command, preview job), candidates' level silences | `analysis.silence_ranges`, `raw_silence_ranges`, `preview_silence` | worker process; inline fallback gated |
| Automix ducking, music ducking | `analysis.speech_lanes`, `anyone_talking_intervals` | worker process |
| Loudness curves (UI refresh) | `loudness_curve.project_curves` | worker process, background: stopped while playing |
| Per-track measurement pools | `analysis.speech_lanes`, `_compensated_ranges` | `priority.gated_map` |
| Clip loudness match pool | `Session.match_clip_loudness` | `priority.gated_map` |
| Level envelopes (cache fill) | `MediaStore.envelope` | checkpoint per chunk |
| Waveform peaks | `MediaStore._base_peaks` | checkpoint per chunk (a no-op when a request thread builds them) |
| Media hashing (import, relink) | `media._sha256` | checkpoint per MB |
| Linked-media resolver | `MediaStore.__init__` | `priority.thread` (background, low QoS) |
| Imports | `MediaStore.import_batch` | `priority.executor`; checkpoint per file |
| Export (mix, stems, regions) | `export._pump`, mastering write | see below |
| Transcription | detached `transcribe_worker` process | own process (follow-up: nice 19 there too) |
| Memory spill | `memory.MemoryBudget._spill` | small `np.save` in the caller's thread; no change |
| Clipboard preview reference | `loudness_curve.speech_levels` | in-process, foreground and cached; follow-up |
| Music report | `music_report` via `speech_lanes` | in-process, foreground (`gated_map` limits it) |
| Onsets (Tab stops) | `onsets.onsets_for_media` | in-process, foreground and cached; follow-up |

## Exports

An export is user-started but runs in the editor's process. So it **pauses
while audio plays**: every render block, on the main loop and on the render
threads, passes `checkpoint`. The UI's exports run as jobs, so they show
"Paused while playing". Running exports in a low-priority subprocess, so that
they could continue during playback, is a follow-up.
`programme.master` (mastering) is one speechmix call and cannot pause in the
middle.

## Not paused, on purpose

- Request threads: the UI waits on them, and they may hold the session lock.
  User-started commands such as Auto-Silence run their heavy part in the
  worker process at nice 19, so they do not take the editor's GIL.
- The recorder and its take import: the recorder outranks playback, and the
  import holds the session lock.
- IO-only helper threads: listed in `tests/test_thread_guard.py`.

## The audio path

- The callback takes only `_tlock`. Nothing in `priority`, `jobs` or `offload`
  takes it; the gate reads `is_playing` without a lock.
- The callback still allocates per block (`mixer.mix` returns new arrays).
  That was there before this change; removing it is a follow-up.
