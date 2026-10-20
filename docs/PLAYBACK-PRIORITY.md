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
  - It takes nice 10 (`offload.WORKER_NICE`), no Darwin background band.
    v26.10.20.2 used nice 19 and the band: imports took 4.7 s instead of
    0.7 s under load, and on the owner's loaded Mac workers ran at ~5% CPU
    for 11+ minutes and never finished. Measured 2026-10-20 at nice 10, load
    average ~10: the curve worker's imports take ~0.6 s and ~100 MB RSS; a
    probe starts and exits in ~0.65 s.
  - When the caller is background work, it does not start while audio plays,
    and a running one is stopped with SIGSTOP while audio plays and continued
    afterwards. Cancel kills it.
  - It exits by itself when the editor is gone: its parent pid changes (or
    is 1), or the pipe on its stdin from the editor closes.
  - A failed or timed-out key backs off: no new worker for it for 5 s, then
    10, 20 ... up to 300 s; a success resets it. The UI's loudness loader
    backs off the same way after a failed request instead of asking again at
    every store change.
  - The editor logs its child processes by module at start and exit, and
    the `-m kuulas...` processes left behind (parent pid 1), so a leak can be
    named from `kuulas.log`.
  - It writes the same content-keyed caches the editor reads.
  - At most one worker process lives at a time (`offload.WorkerManager`).
    v26.10.20.2 started one per call and stopped each while playing: loudness
    refreshes after edits left ~35 stopped workers and the Mac ran out of
    memory. Now calls queue (capped at `MAX_QUEUED`). A newer loudness request
    for the same project ends the older one (HTTP 409). Background work does
    not start a worker while audio plays. A user's command preempts a stopped
    background worker, which starts again later.
  - Every worker is killed and reaped on cancel, error, timeout (`WALL_S` of
    running time), project close and exit (`atexit`). A watchdog kills a
    worker its waiting thread no longer looks after and continues one left
    stopped after playback.
  - If the editor dies, a stopped worker's process group is orphaned and the
    kernel continues and hangs it up; a running worker sees its parent gone
    and exits. At start, `sweep_orphans` kills this user's
    `-m kuulas.analysis_worker` processes whose parent is gone (never the
    transcription worker).
  - Fail soft: a store it cannot reopen, or a worker that does not answer, is
    measured in the editor under the gate, with a log line.
  - The bundle runs it via `bundle.worker_module` / `_run_analysis_worker`.
    Its log is `kuulas-analysis.log`.
  - `--selftest` checks that it starts at nice 10.
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
  worker process at nice 10, so they do not take the editor's GIL.
- The recorder and its take import: the recorder outranks playback, and the
  import holds the session lock.
- IO-only helper threads: listed in `tests/test_thread_guard.py`.

## The audio path

- The callback takes only `_tlock`. Nothing in `priority`, `jobs` or `offload`
  takes it; the gate reads `is_playing` without a lock.
- The callback still allocates per block (`mixer.mix` returns new arrays).
  That was there before this change; removing it is a follow-up.
