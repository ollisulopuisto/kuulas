# Local transcription queue, 29 October 2026

Owner: Kuulas orchestration lane, `fix/local-transcription-queue`, separate from
Inspector and Viewer. No active overlapping transcription owner reported.

Detached local workers wait in arrival order on a per-user machine-local queue
before invoking Orukeet. OS advisory locking excludes concurrent model workers
across projects/processes and releases after process death. Waiting status keeps
a live worker PID and a localized message, so it stays queued rather than being
classified as interrupted after 60 seconds. Existing cancel-file watcher remains
active while waiting; cancelled jobs never enter the local engine. Cloud jobs do
not take this local slot. External tool guard and memory eligibility checks stay.

No model installed or run for verification. Fake engines test serial admission,
queued cancellation, engine-failure cleanup and actual cross-process exclusion
plus lock release after kill. 48 focused worker/transcribe/queue/messages tests
pass. This serializes Kuulas-launched work, not unrelated external CLI invocations;
the external CLI still owns its protective guard. No retry loop hides a real
engine failure. UI already displays queued/running states and cancel actions.

Known native acceptance gap: real Orukeet/model load, multiple actual Mac windows,
app closure/reopen and cancellation on the owner's machine. No native claim.
