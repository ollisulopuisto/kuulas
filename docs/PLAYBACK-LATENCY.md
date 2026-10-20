# Playback latency and the playhead

How the cursor follows the sound, what was measured, and how to check by ear.

## How it works (2026-10-20)

- **Anchors, not a position stream.** `engine.status()` gives the heard frame plus
  `t`, the monotonic time it was heard at (the callback that produced it, or later
  while a run's first frames are still in the device), and `seq`, which changes on
  every transport change. The live channel (`/api/live`) sends an `anchor` at once on
  play/seek/stop/speed (the transport request publishes it) and a correction every
  200 ms while playing (`LIVE_CORRECT_S`). It reads the engine on its own thread, not
  the default executor, and never sends an anchor older than one already sent.
- **The browser extrapolates** (`ui/playhead-clock.js`) every animation frame from the
  latest anchor: speed, reverse, skips, loop wrap, run end. Small backward corrections
  (under 50 ms) are absorbed, bigger ones snap. Clock offset: five pings at connect
  and one every 10 s; the quickest round trip gives offset = server time - midpoint.
- **Stop is instant.** Space freezes the cursor at once; the engine aborts the
  PortAudio stream so nothing already queued is heard, and the stop's answer lands the
  cursor on the engine's heard frame. A seek or play that jumps more than 50 ms while
  playing does the same, then restarts the stream.
- **Buffer.** The stream asks for `latency="low"`; two late blocks within 5 s raise it
  to `"high"` and 2048 frames.

## Measured on the Mac Studio (2026-10-20, silent output, no listening test)

| | internal speakers | DENON-AVR |
|---|---|---|
| `stream.latency`, block 1024 ("low" = "high") | 34.8 ms | 35.3 ms |
| DAC lead reported per callback | 14.7 ms | 35.3 ms |
| callback interval, spread | 21.3 ms, < 0.1 ms | 21.3 ms, < 0.1 ms |
| `stream.abort()` returns after | ~105 ms | ~115-140 ms |
| `stream.start()` after an abort | 4-10 ms | 9-14 ms |

On Core Audio the block size, not the latency setting, sets the buffer (512 frames:
24 ms, 256: 19 ms with uneven callbacks). The abort's ~100 ms is PortAudio polling
the stopped unit; the sound should end when the unit is stopped, at the start of the
call. That is from PortAudio's source, not measured by ear.

`GET /api/transport` returns `latency`: `stream_ms`, `block_ms`, `dac_lead_ms`,
`callback_ms`, `jitter_ms`, `estimate_ms` (what the playhead subtracts) and
`measured_ms` (block + DAC lead as the host API reports it). Neither is end to end:
a Bluetooth/AirPlay/receiver delay is outside what PortAudio sees.

## Checking by ear and on video

1. Open a project with a clear transient (a clap, a plosive) and zoom in until a
   second is a few hundred pixels wide.
2. Play over it. The cursor should cross the transient's start in the waveform as you
   hear it. Film the screen with a phone at 240 fps (slow motion): count frames between
   the cursor reaching the transient and the sound on the video's audio track.
3. Press Space in the middle of a word: the sound must stop at once, and the cursor
   should rest where the sound stopped (resume with Space: the word continues).
4. Click far away while playing: no sound from the old place after the click.
5. `curl -s localhost:<port>/api/transport | python3 -m json.tool` while playing shows
   the `latency` numbers above.
