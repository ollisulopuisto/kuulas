# Recording health and live-view follow-up

## Findings

- The recorder already detects PortAudio input overflows and recorder-ring backlog.
  It warns during recording and records counts/events in the take metadata and journal.
- The post-import notice currently reports gaps and failed channels, but does not
  report input-overflow counts or the duration of inserted silence.
- The overview strip uses only `projectEnd(project)`, so it cannot grow to include
  the active, not-yet-imported take.
- Live waveform columns currently scan every sample since Record on each level event
  (about ten updates per second). That work grows with take duration even when only
  a small time window is visible.

## Changes in this worktree

- Add a concise post-import health summary for input overflows and recorder-inserted
  silence, in English and Finnish. Keep the detailed event records in the take files;
  explain the summary in the recording help and keep its notice open until dismissed.
- Extend overview time bounds through the live recording head and redraw the overview
  as the take advances.
- Limit live-waveform column generation to samples intersecting the visible timeline
  window (including the preceding sample needed to fill the first partial column).
- Skip repainting the dimmed timeline behind the recording modal; refresh it once when
  the modal closes.

No real microphone run is available here. The owner should confirm the overview grows,
the recording view stays responsive during a long take, and the import notice reports
any simulated or real overflow/dropout.
