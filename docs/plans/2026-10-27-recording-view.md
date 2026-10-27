# Recording display and dialog implementation plan

Goal: one combined v26.10.27.4 release, including the already merged TLS and
toolbar changes. The owner cancelled the standalone v26.10.27.3 build.

1. Regression: recording begins with null/new track ids; later binding must retain
   received peaks and draw them immediately. Also preserve peaks received before
   the plan exists. Red/green pure tests, then a browser simulation of API/WS order.
2. Use waveformColumns for live wave geometry too: obey half/full mode, scale and
   height. Draw the recording head from time even when input is silent.
3. Actual per-input three-second LUFS during recording, with -23/-16 references and
   an independent immediate peak-clip warning. Preserve recorder isolation: do not
   import the editor/DSP into kuulas_recorder or modify its callback/writer path.
   An editor-owned, bounded low-priority worker reads only flushed progressive WAV
   audio, incrementally, using the shared speechmix ShortTermAccumulator adapter.
   No writes, no history edits, no microphone access. Setup's pre-record input peak
   check remains explicitly dBFS; capture loudness appears once three seconds exist.
4. Redesign setup: input and channel routing/meter are primary; remaining settings
   under More options. Clear Record/Cancel footer. Recording: compact take/time,
   channel LUFS, marker and Stop; no huge warning blocks or oversized ring. Keep
   stop safety modes and hiding-without-stopping behavior intact.
5. Test red/green for binding, geometry, file-growth/channel LUFS reference values,
   missing/partial files, safe paths, stale values and shutdown. Browser checks for
   compact setup/live layouts and both new/existing track progress. Full Python,
   Node, Ruff, Biome and packaged HTTPS probes before combined publication.

The live-transcription proposal remains a roadmap feasibility item, not an
implementation in this release. Ultra remains deferred pending shared-tool work.

Implemented and checked with synthetic recorder audio and Chrome API/WebSocket event-order tests: delayed new-track IDs retain peaks, input LUFS agrees with the shared reference, clipping stays independent, setup fits without scrolling, and two-step Stop remains intact. Real microphone capture remains an owner check. PRs #41 and #42 security changes are included.
