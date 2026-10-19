# kuulas-recorder

The standalone recording program (WP12a part A, `src/kuulas_recorder/`). The
editor is only a client: it starts the recorder, sends commands on a local
socket and shows what the recorder reports. Quitting or crashing the editor
never stops a recording.

**The rule that decides every choice here (owner, 2026-10-18): audio already
recorded is never lost.** A file from a killed recorder, a crashed machine or
a pulled cable opens with everything up to the last flush. Nothing needs a
clean stop to become readable.

`kuulas_recorder` imports nothing from `kuulas` (the editor) and nothing but
numpy, sounddevice and the standard library (tested:
`tests/test_recorder_isolation.py`). The editor may import
`kuulas_recorder.client`; never the other way round.

Contents: [architecture](#architecture), [running it](#running-it),
[the protocol](#the-protocol), [files](#files), [failures](#failures-what-happens-and-what-is-guaranteed),
[measurements](#measurements), [for the editor (part B)](#for-the-editor-part-b),
[how the editor uses it](#how-the-editor-uses-it-part-b-built-2026-10-19),
[open problems](#open-problems).

## Architecture

```
 editor (any number of clients, may come and go)
        |  JSON lines over a Unix socket
        v
 supervisor  (kuulas-recorder serve)       never loads PortAudio
   - socket, clients, the take's journal and sidecar
   - starts / restarts the worker, repairs its files after a death
   - free disk space, device-loss polling, caffeinate
        |  stdin: config + "stop"     stdout: JSON events
        v
 worker  (python -m kuulas_recorder worker)   one per segment
   - audio callback: copy the block into a preallocated ring, count, return
   - writer thread: ring -> one progressive WAV per armed channel,
     flush (sync audio, rewrite header, sync) every 1 s of audio
   - reporter thread: events to the supervisor, never blocking the writer
```

Why two processes: Python's lock stalls the audio thread when other threads
work (measured 20 to 58 ms in playback, WP2), and a crash in the audio driver
or the capture code must not take the socket, the journal and the take with
it. The supervisor does no audio work at all; the worker does nothing else.

- **The callback** (`capture.Ring.push`) copies into a ring slot sized at
  start (20 s of audio), stores the arrival time and the overflow flag, and
  advances an index. No allocation of audio buffers, no lock, no file, no
  exception escapes (`SoundDeviceSource._callback` swallows and counts).
- **If the writer falls behind by the whole ring** (a disk that stalls for
  20 s), the callback drops blocks and counts the frames; the writer then
  writes the same number of frames of silence, so every channel stays on the
  recording clock, and reports a `dropout`.
- **A host input overflow** (`status.input_overflow`: audio lost before the
  callback saw it) is counted with its position. Its length is unknown, so
  nothing is inserted.
- **Device lost**: the source says so (`finished_callback`), or no callback
  came for 1 s (5 s for the first block). The worker flushes, closes and
  exits with code 2; the supervisor asks a fresh process for the device list
  every second and, when a device with the same name is back, starts a new
  worker into the next segment.
- **Worker died** (crash, SIGKILL, hang): the supervisor repairs the files of
  its segment, journals `worker_died` and the gap, and starts a new worker
  into the next numbered file set after a back-off (0.2 s doubling, at most
  5 s). A worker silent for 30 s (longer than its ring) is killed and
  restarted. Five deaths in a row without a single flush stop the take with
  `worker_keeps_failing` instead of a crash loop.
- **Sleep**: while a take records, `caffeinate -i -m -w <supervisor pid>` keeps
  macOS from idle sleep and disk sleep; `-w` makes it exit with the
  supervisor, even after a SIGKILL. Closing a laptop lid still sleeps the
  machine; no user process can stop that. Windows will use
  `SetThreadExecutionState`; Linux has nothing yet.
- **Ctrl+C** in a terminal reaches the whole process group: the worker ignores
  SIGINT; the supervisor treats SIGINT and SIGTERM alike (stop the take
  cleanly, everything flushed, then exit). SIGHUP is ignored.
- **The supervisor killed alone**: the worker's stdin closes, so it stops
  itself cleanly rather than record on with nobody able to stop it.
- **One recorder per user**: `recorder.lock` (flock) in the state folder; a
  second `serve` exits with "Another kuulas-recorder is already running."

Rate: the take is recorded at the rate asked for (the project rate, 48000).
A device not running at that rate is refused with a message naming its rate
(`device_rate_mismatch`), checked before anything opens; on CoreAudio the
stream is also opened with `fail_if_conversion_required`, so CoreAudio never
resamples behind our back. There is no live resampling, ever.

## Running it

```
kuulas-recorder serve [--socket PATH] [--state-dir DIR] [--flush-seconds 1.0]
kuulas-recorder devices [--json]          # input devices
kuulas-recorder repair FILE.wav ...       # repair WAVs left by a crash
kuulas-recorder send CMD ['{"json": 1}']  # one command, print the answer
kuulas-recorder watch [--levels]          # print events as they come
```

`python -m kuulas_recorder ...` is the same. The editor starts it with
`kuulas_recorder.client.spawn_supervisor()`, which runs `serve` in its own
session (`setsid`), with no tie to the editor's terminal or process group.

**Socket path.** macOS limits a socket path to 104 bytes, so it lives in a
short per-user folder: `KUULAS_RECORDER_SOCKET` if set; on macOS
`~/Library/Application Support/kuulas/recorder/rec.sock`; on Linux
`$XDG_RUNTIME_DIR/kuulas/rec.sock` (or `~/.local/state/kuulas/rec.sock`); if
that is too long, `/tmp/kuulas-<uid>/rec.sock`. The folder is mode 0700, the
socket 0600. The transport sits behind `transport.Listener` / `Connection`
(`accept`, `read_line`, `send`, `close`) so a Windows named pipe can be added
without touching the supervisor or the client.

**State folder** (default: the socket's folder): `recorder.log` (rotating,
UTC times), `worker.log` (the workers' stderr: tracebacks),
`recorder.lock`, and `current.json` while a take records (what to recover
if the recorder is killed).

**Tests without a device.** `KUULAS_RECORDER_FAKE=<spec.json>` makes the
worker record from a fake device and `devices` list the spec's devices. The
spec holds `devices` and flags a test flips while it runs: `unplugged`,
`stall`, `overflow`, plus `epoch_ns`. Never set it outside tests.

**Microphone permission** (owner, 2026-10-19): the .dmg app carries the usage
text; a development run from a terminal needs the terminal allowed in System
Settings > Privacy & Security > Microphone. Without it CoreAudio delivers
silence, not an error: check the levels.

**Hardware test**: `uv run pytest -q -s tests/hardware/test_record.py` records
5 s from the default input through the whole recorder and prints levels and
the file path.

## The protocol

Newline-delimited JSON over the socket, UTF-8, one object per line, at most
1 MB a line. Protocol version: `PROTOCOL = 1` (`hello` reports it).

**Requests** carry `cmd` and an optional `id` that the answer echoes:

```json
{"id": 7, "cmd": "status"}
```

**Answers**: `{"id": 7, "ok": true, ...result}` or

```json
{"id": 7, "ok": false, "error": {"key": "not_recording", "text": "No take is recording."}}
```

The `key` is stable and machine-readable; the `text` is plain English for
logs. The editor shows its own translated message for the key.

**Events** (pushed to clients that subscribed) carry `event` instead of `id`:

```json
{"event": "gap", "take": "take-003", "at_frame": 1440000, "frames": 31200, "reason": "worker_restart", "segment": 2}
```

Commands run one at a time per connection; open several connections for
parallel work. A client that does not read its answers and events is
disconnected once 512 messages are queued for it or a send blocks for 5 s; it
never slows the recording.

### Commands

| Command | Fields | Answer |
|---|---|---|
| `hello` | `subscribe`, `levels` (optional, as `subscribe`) | `protocol`, `version`, `pid`, `status` |
| `ping` | | `pong: true`, `utc` |
| `subscribe` | `events` (default true), `levels` (default false) | the same two flags |
| `devices` | | `devices`: `[{index, name, channels, default_rate, hostapi, default}]` (inputs only) |
| `start` | `folder` (absolute), `take`, `channels` (1-based, default `[1]`), `names` (default `ch<n>`), `rate` (default 48000), `device` (index, name, `{index, name}` or absent for the default input) | the status, plus `warning` when space is low |
| `arm` | `preroll_s` (above 0, at most 600), `channels` (default `[1]`), `rate`, `device` (as `start`) | the status, with `armed: {device, channels, rate, preroll_s}` (WP12c; see [pre-roll](#pre-roll-wp12c)) |
| `disarm` | | the status; harmless when not armed |
| `stop` | | `take`: `{folder, take, stop_reason, frames, sidecar}` once every file is closed |
| `status` | | the status (below) |
| `levels` | | `names`, `peak_dbfs` (per armed channel since this client's last call, floor -120), `clipped` |
| `mark` | `text` (up to 1000 characters) | `at_frame`, `text`, `utc` |
| `repair` | `folder`, `take` | `folder`, `take`, `state`, `frames`, `files`, `sidecar` |
| `quit` | | `quitting: true` (refused with `busy` while recording) |

Examples:

```json
{"id": 1, "cmd": "hello", "subscribe": true}
{"id": 1, "ok": true, "protocol": 1, "version": "26.10.19.19", "pid": 4242, "status": {"state": "idle", "pid": 4242, "worker_pid": null, "last_take": null, "recovered": []}}

{"id": 2, "cmd": "devices"}
{"id": 2, "ok": true, "devices": [{"index": 3, "name": "Scarlett 2i2", "channels": 2, "default_rate": 48000.0, "hostapi": "Core Audio", "default": true}]}

{"id": 3, "cmd": "start", "folder": "/Users/me/Show.kuulas/recordings", "take": "take-001", "channels": [1, 2], "names": ["Host", "Guest"], "device": {"index": 3, "name": "Scarlett 2i2"}}
{"id": 3, "ok": true, "state": "recording", "take": "take-001", "folder": "...", "start_utc": "2026-10-19T10:15:02.120Z", "position_frames": 4800, "...": "..."}

{"id": 4, "cmd": "levels"}
{"id": 4, "ok": true, "names": ["Host", "Guest"], "peak_dbfs": [-18.2, -120.0], "clipped": [false, false]}

{"id": 5, "cmd": "mark", "text": "good answer"}
{"id": 5, "ok": true, "at_frame": 2880000, "text": "good answer", "utc": "2026-10-19T10:16:02.120Z"}

{"id": 6, "cmd": "stop"}
{"id": 6, "ok": true, "take": {"folder": "...", "take": "take-001", "stop_reason": "stopped", "frames": 2976000, "sidecar": ".../take-001.take.json"}}
```

**Status** fields: `state` (`idle`, `checking`, `arming`, `armed`,
`disarming`, `starting`, `recording`,
`restarting`, `device_lost`, `stopping`), `pid`, `worker_pid`, `last_take`,
`recovered` (takes repaired at this recorder's start), and while a take is on:
`take`, `folder`, `device`, `channels`, `rate`, `start_utc`,
`position_frames` (now, on the take's clock), `preroll_frames` (the part of
the take heard before Record, 0 without pre-roll), `frames_flushed` (durable on
disk), `segments`, `gaps`, `dropouts`, `overflows`, `worker_restarts`,
`markers` (count), `disk` (`free_bytes`, `seconds_left`).

### Events

| Event | Fields | When |
|---|---|---|
| `started` | `take`, `folder`, `start_utc`, `device`, `channels` | the first audio arrived |
| `level` | `peak_dbfs`, `clipped`, `position_frames` | ~10 a second, only with `levels: true` |
| `warning` | `key`, `text`, more by key | `disk_low` (`seconds_left`, `free_bytes`) at 30, 10 and 2 minutes left; `input_overflow` (`at_frame`, `count`, at most once a second); `dropout` (`at_frame`, `frames`) |
| `device_lost` | `take`, `device`, `reason`, `at_frame`, `text` | the input stopped |
| `device_back` | `take`, `device` | it is listed again; a new worker is starting |
| `gap` | `take`, `at_frame`, `frames`, `reason` (`worker_restart`, `device_lost`), `segment` | a new segment got its first audio |
| `worker_restarted` | `take`, `exit`, `restarts`, `text` | the worker died and is being restarted |
| `marked` | `take`, `at_frame`, `text`, `utc` | a client sent `mark` |
| `error` | `key`, `text` | `disk_full`, `worker_keeps_failing` (the take then stops) |
| `armed` | `device`, `channels`, `rate`, `preroll_s` | the input delivers audio and is being listened to (WP12c) |
| `disarmed` | `reason` (`disarmed`, `rearmed`, `expired`, `shutdown`, `device_lost`, `worker_died`), `text` | the recorder stopped listening; nothing was recorded |
| `stopped` | `folder`, `take`, `stop_reason`, `frames`, `sidecar` | the take is over and every file closed |

### Error keys

`bad_request`, `unknown_command`, `bad_name`, `already_recording`,
`not_recording`, `busy`, `take_exists`, `folder_not_writable`, `disk_full`,
`device_list_failed`, `device_not_found`, `channels_unavailable`,
`device_rate_mismatch`, `device_open_failed`, `device_no_audio`,
`file_exists`, `worker_failed`, `take_not_found`, `armed_mismatch` (a `start`
for other channels or another input than the armed one), `already_running` (from
`serve`), `internal`; and from the client library `timeout`,
`disconnected`, `spawn_failed`.

Names (`take`, `names`): letters of any script, digits, space and
`- _ . , ( ) ' +  &`, up to 80 characters, no leading dot or space, no `~`.

## Pre-roll (WP12c)

"You can never start recording too late" (owner, 2026-10-19). `arm` opens the
input in a worker that **listens**: it keeps the last `preroll_s` seconds of the
armed channels in memory (float32, whole blocks, trimmed to the exact length at
Record) and writes **nothing**: no file, no sidecar, no journal, no
`current.json`. Memory is bounded: `preroll_s` x rate x 4 bytes a channel (a
minute of one channel at 48 kHz is 11.5 MB), plus one block. The meters run, so
`level` events flow while armed.

- **Record** is an ordinary `start` while armed. The supervisor sends the
  listening worker `record`; it opens the files, writes the buffered audio
  first and goes on. The take's frame 0 is the oldest buffered frame, so
  `position_frames` already counts the pre-roll when `start` answers, and the
  sidecar says `preroll_frames` (the frame where Record was pressed; 0 when
  nothing was armed or nothing was heard yet). Less than `preroll_s` is used
  when the recorder listened for less.
- `start` must ask for the armed channels, rate and (when it names one) input,
  or it is refused with `armed_mismatch` and the recorder stays armed. A refused
  `start` (`take_exists`, disk) leaves it armed too.
- **The microphone is let go by itself**: `arm_ttl` (default 120 s) after the
  last `arm`. Arming again with the same settings only extends it (a keepalive;
  the editor repeats it every 20 s while its record view is open), so a closed
  or crashed editor never leaves a microphone listening. `disarm`, a different
  `arm`, `quit` and shutdown also end it. A lost input or a dying worker ends
  it with `disarmed` (`device_lost`, `worker_died`): there is no recovery to
  do, nothing was written.
- Nothing is written, so a crash while armed leaves nothing to repair, and
  the buffer is gone with the process (privacy).
- `stop` while only armed is `not_recording`; `arm` while recording is
  `already_recording`.
- The editor places the clip so that the pre-roll ends where Record was pressed
  (`record_take.clip_plan`): at `at + start_frame - preroll_frames`, with what
  would fall before the start of the timeline cut from the clip's head.

## Files

All in the `folder` given to `start` (the editor uses
`<project>.kuulas/recordings/`, owner decision 2026-10-19, so a project stays
one self-contained thing; Dropbox syncs the files while they grow, which is
harmless but uses bandwidth).

| File | What |
|---|---|
| `<take>-<name>.wav` | the first segment of one armed channel |
| `<take>-<name>~<n>.wav` | segment `n` (2, 3, ...): after a worker restart, a device return or the size limit |
| `<take>.take.json` | the snapshot: where everything sits on the recording clock |
| `<take>.journal.jsonl` | append-only log of everything that happened |

A take or file is never overwritten: `start` refuses a take whose files
exist (`take_exists`), and every WAV is created with `O_EXCL`.

### The WAV files

Mono, 24-bit little-endian PCM, plain `WAVE_FORMAT_PCM` header of 44 bytes,
data chunk last, at the take's rate. **Never compressed.** 24-bit and not
32-bit float: the plan asks for it, every tool reads it, a converter has no
more than 24 bits to give, and it is a quarter smaller (144 000 bytes a
second at 48 kHz, so one file holds 8.2 hours; a longer take continues in the
next numbered file without losing a frame).

**Progressive**: the header is written and synced before any audio. Audio is
appended with `os.write` (nothing buffered in Python). Every 1 s of audio (or
1 s of wall time when audio trickles) each file is flushed: sync the audio
(`F_BARRIERFSYNC` on macOS, so the audio reaches the disk before the
header), rewrite the RIFF and data sizes in one 44-byte `pwrite`, then
`F_FULLFSYNC` (through the drive's own cache). The header never names audio
that is not on disk. At any moment the file is a valid WAV of everything up
to the last flush; bytes after it are past the data size and every reader
ignores them. Plain `fsync` is used where `F_FULLFSYNC` is refused (network
shares, FAT).

`repair_wav(path)` (and `kuulas-recorder repair`, and the `repair` command)
sets the data size to every whole frame present (taking back audio written
after the last flush), cuts off a partial last frame, fixes the RIFF size,
rebuilds a header that never reached the disk, and refuses a file that is not
a WAV (`not_a_wav`) without touching it. The recorder repairs a crashed
take's files when it next starts, and every segment's files whenever a worker
dies.

### `<take>.take.json`

Replaced atomically (temporary file, fsync, rename, fsync of the folder) at
every flush and every event, so it is always whole. The WAV files are the
truth for how much audio there is; after a crash the snapshot may lag by one
flush, and recovery reads the files.

```json
{
 "format": 1,
 "recorder_version": "26.10.19.19",
 "take": "take-001",
 "state": "stopped",
 "stop_reason": "stopped",
 "created_utc": "2026-10-19T10:15:01.902Z",
 "updated_utc": "2026-10-19T10:17:04.551Z",
 "start_utc": "2026-10-19T10:15:02.120Z",
 "start_monotonic_ns": 912873465120,
 "rate": 48000,
 "sample_format": "pcm_s24le",
 "preroll_frames": 0,
 "device": {"index": 3, "name": "Scarlett 2i2", "channels": 2, "default_rate": 48000.0, "hostapi": "Core Audio", "default": true},
 "channels": [{"channel": 1, "name": "Host"}, {"channel": 2, "name": "Guest"}],
 "segments": [
  {"segment": 1, "start_frame": 0, "start_flicks": 0, "end": "worker_died",
   "files": {"Host": {"file": "take-001-Host.wav", "frames": 1440000},
             "Guest": {"file": "take-001-Guest.wav", "frames": 1440000}}},
  {"segment": 2, "start_frame": 1471200, "start_flicks": 21626640000, "end": "stopped",
   "files": {"Host": {"file": "take-001-Host~2.wav", "frames": 4504800},
             "Guest": {"file": "take-001-Guest~2.wav", "frames": 4504800}}}
 ],
 "frames": 5976000,
 "gaps": [{"at_frame": 1440000, "frames": 31200, "reason": "worker_restart"}],
 "dropouts": [],
 "overflows": 0,
 "overflow_at": [],
 "markers": [{"at_frame": 2880000, "text": "good answer", "utc": "2026-10-19T10:16:02.120Z"}],
 "worker_restarts": 1
}
```

- `state`: `recording` (a recorder is writing it, or was when it died),
  `stopped`, or `interrupted` (repaired after a crash; `stop_reason`
  `recorder_crashed`). `stop_reason`: `stopped`, `shutdown` (SIGTERM/SIGINT),
  `disk_full`, `worker_keeps_failing`, `recorder_crashed`.
- **The recording clock**: frame 0 is the first captured frame of segment 1,
  at `start_utc` (wall clock, UTC) and `start_monotonic_ns` (the machine's
  monotonic clock, which is shared by all processes on macOS and does not
  run during sleep, which the recorder prevents). The first frame's time is
  the first block's arrival minus one block; the host's input latency (a few
  ms) is not subtracted.
- `segments[].start_frame` / `start_flicks` (1/705 600 000 s): where the
  segment's first frame sits on the take's clock. A segment after a worker
  restart or a device return is placed by the monotonic time of its first
  block, so the gap before it is real time; measured within 332 frames
  (7 ms) of the true position in six runs with the fake device, tested
  within 4096 frames. A segment after the
  size limit starts on the very next frame. A segment whose start was never
  logged (a crash at exactly that moment) is placed right after the one
  before it and carries `"start_unknown": true`.
- `files[name].frames`: frames on disk in that file (channels of one
  segment can differ by a block after a crash).
- `gaps`: time with no audio between segments. `dropouts`: silence written to
  keep sync when the writer fell behind. `overflows` / `overflow_at` (first
  1000 positions): the host lost input.
- `markers`: from `mark`, on the take's clock.

### `<take>.journal.jsonl`

One JSON object a line, appended and fsynced per line; a line a crash cut
short is skipped by readers (`journal.read_journal`). Every line has `utc`
and `event`: `started`, `mark`, `segment` (size-limit rollover), `gap`,
`dropout`, `overflow`, `device_lost`, `device_back`, `worker_died`,
`worker_restarted`, `worker_stuck`, `disk_low`, `disk_full`, `stopped`,
`recovered`.

## Failures: what happens and what is guaranteed

| Failure | What happens | Guaranteed | Test |
|---|---|---|---|
| The editor quits or crashes | nothing; the take goes on | a client reconnecting gets the running state | `test_closing_the_client_does_not_stop_the_recording` |
| A client stops reading | it is disconnected | recording and other clients unaffected | `test_a_client_that_stops_reading_is_dropped_and_recording_goes_on` |
| Worker killed (SIGKILL) or crashes | files repaired; new worker into `~<n>` files; `worker_restarted`, `gap` | everything flushed is kept; the gap is measured and journaled | `test_killing_the_worker_restarts_into_a_new_numbered_file` |
| Worker dies again and again | stops after 5 deaths without a flush, `worker_keeps_failing` | no crash loop; the take is closed | `test_a_worker_that_keeps_dying_is_not_restarted_forever` |
| Worker hangs | killed after 30 s of silence, then as above | | (watchdog; not tested with a real hang) |
| Supervisor killed alone | worker sees stdin close, flushes, closes | complete, closed files | `test_supervisor_killed_alone_lets_the_worker_close_its_files` |
| Everything SIGKILLed / power cut / crash | nothing runs | every file opens as it is, with all audio up to the last flush (1 s); next start repairs it, takes back later audio that reached the disk, marks the take `interrupted` and lists it in `recovered` | `test_sigkill_of_the_whole_recorder_leaves_readable_files` |
| Truncated or cut file | `repair_wav` | trailing partial frame trimmed, sizes right | `test_recorder_wav.py` (repair tests) |
| SIGTERM / SIGINT / Ctrl+C | take stopped cleanly, then exit | everything flushed and closed, `stop_reason: shutdown` | `test_sigterm_flushes_and_closes_the_take`, `test_sigint_is_a_clean_stop_too` |
| Device unplugged / stalls | `device_lost`; files flushed; polls every 1 s; `device_back`, `gap`; new segment | nothing recorded is lost; the take goes on when the device returns | `test_device_unplug_and_return_continue_the_take`, `test_device_loss_is_noticed_when_callbacks_stop` |
| Stop while the device is gone | take closed | | `test_stop_while_the_device_is_gone_ends_the_take` |
| Device opens but sends nothing | start refused, `device_no_audio`, no files left | | `test_a_device_that_sends_no_audio_is_refused_at_start` |
| Device at the wrong rate | start refused naming the rate | no resampling, no files | `test_wrong_rate_is_refused_with_the_device_rate` |
| Disk getting full | `disk_low` warnings at 30 / 10 / 2 min left | | `test_disk_warnings_then_a_graceful_stop_before_it_is_full` |
| Disk nearly full (10 s left above a 200 MB reserve) | graceful stop, `error disk_full`, `stopped` | everything flushed and closed | same |
| Disk full anyway (a write fails) | the worker keeps every whole frame written, cuts a partial one, flushes headers, exits; take stopped `disk_full` | the file is valid with all audio before the error | `test_full_disk_stops_with_everything_written_flushed`, `test_a_full_disk_in_the_worker_ends_the_take`, `test_full_disk_keeps_the_file_valid_with_what_was_written` |
| Not enough space to start | refused, `disk_full` | | `test_start_is_refused_when_the_disk_is_full` |
| Disk stalls (slow USB disk, network) | ring absorbs 20 s; beyond that, silence keeps the sync and a `dropout` warning | the timeline stays aligned | `test_writer_stall_becomes_silence_not_a_shift` |
| Input overflow | counted, journaled, warned (once a second) | | `test_overflow_is_counted` |
| Hours of recording | ring and files fixed in size; next file at the 8.2 h limit | memory does not grow | `test_hours_of_audio_run_in_bounded_memory` (3 h), `test_size_limit_continues_in_the_next_numbered_file_without_a_lost_frame` |
| An existing take | refused, `take_exists` | never overwritten | `test_an_existing_take_is_never_overwritten`, `test_existing_take_file_is_never_overwritten` |
| Second recorder started | refused, `already_running` | | `test_only_one_supervisor_runs_per_state_folder` |

**Not guaranteed:**

- Audio after the last flush (up to 1 s, plus whatever the 20 s ring held) is
  lost when the worker or the machine dies. On a SIGKILL of the worker alone
  the operating system still writes what the worker had written, and the
  repair takes it back; on a power cut only what was synced survives.
- Audio during a gap is not recorded: nothing can. A worker restart gap
  measured 0.18 to 0.21 s with the tests' 10 ms back-off (add the default
  0.2 s back-off in real use); a device loss costs the 1 s it takes to notice
  plus the time the device is away plus up to 1 s of polling.
- The recorder cannot keep a laptop awake with its lid closed, and cannot
  record when macOS denies the microphone (CoreAudio then delivers silence;
  the editor should check the levels).
- Python can stall the audio thread (the GIL). The callback is tiny and the
  worker has no busy thread, but a host overflow is still possible under
  heavy machine load; it is counted, never silent.
- A worker that hangs inside CoreAudio is only detected by the 30 s watchdog.
- Positions of later segments are accurate to about a block, not to a frame.

## Measurements

On the owner's Mac Studio (M1 Max), 2026-10-19:

- Syncing (`wavfile.full_sync`, 144 kB written before each): `fsync` 0.09 ms
  median; `F_BARRIERFSYNC` 0.81 ms median, 1.4 ms worst; `F_FULLFSYNC` 4.2 ms
  median, 27 ms worst. A flush costs one of each per file per second, in the
  writer thread (the GIL is released while it waits).
- Callback timing (`tests/manual/test_recorder_bench.py`; a thread playing
  the driver calls the callback every 21.3 ms while the writer writes and
  syncs real files): the callback itself runs 0.016 ms median, 0.07 ms worst
  (1 channel), 0.024 / 0.26 ms (8 channels). Its lateness, 0.26 ms median and
  1.0 ms worst, equals the emulating thread's own timer lateness with no
  writer at all (0.23 / 1.0 ms): the writer costs the callback nothing
  measurable. With a thread that never sleeps holding the GIL, lateness rose
  to 4.2 ms median and 22 ms worst at Python's default 5 ms switch interval,
  and 1.7 / 4.1 ms at 1 ms, so the worker sets a 1 ms switch interval. No
  frame was dropped in any run.
- Gaps, with the fake device: a worker restart 0.18 to 0.21 s (10 ms
  back-off), the next segment placed within 332 frames (7 ms) of where its
  audio really was.
- Three hours of audio through callback, ring and writer at full speed: no
  memory growth beyond 256 kB after the first ten minutes (the test bound).

## For the editor (part B)

- Start the recorder with `client.spawn_supervisor()` if `hello` fails to
  connect, then always talk to it through `RecorderClient`. Do not stop it
  when the editor quits. `quit` only when idle, if at all.
- `hello` with `subscribe: true` gives the state at once: after the editor
  restarts, a `state` other than `idle` means "show the record view again".
- **The take is ready to import when** its `stopped` event arrives, or its
  sidecar says `stopped` or `interrupted`. Place each segment's files at
  `start_frame` (relative to where the take began on the timeline), one clip
  per channel per segment, all in one sync group. Gaps are real silence
  between clips; a dropout is silence inside a file. Show `overflows`,
  `dropouts`, `gaps` and `worker_restarts` to the user.
- The files are linked in place (`recordings/` is inside the project); never
  copy or transcode them. They are plain WAVs readable at any moment, also
  while recording, so a growing take can be shown or played (read only the
  frames the header names).
- **Crash recovery**: `status.recovered` lists takes the recorder repaired at
  its start; also offer `repair` for any `<take>.take.json` still saying
  `recording` when no recorder is running it.
- **Device choice**: send `device` as `{index, name}`; the name wins when
  indexes change after replugging.
- `levels` is per connection (peak since that connection's last call); the
  `level` event stream is the cheaper choice for meters.
- `mark` is the recorder's own marker list (in the sidecar and journal). The
  record view's richer log (rename, move, delete, cut candidates; WP12's
  `PUT /api/record/log`) is the editor's to keep; it can write it beside the
  take, keyed on the same take clock (`position_frames`).
- `stop` has no hold-to-stop check: the 2 s hold is the editor's gesture.
- **Differences from the WP12 text** (written before this design): no
  `.partial` files and no rename at stop (the WAV is valid all the time);
  the sidecar is `<take>.take.json`, not `<take>.json`; a device loss
  continues the same take as a new segment with a gap (the editor can still
  show segments as clips in one sync group).
- Event texts are English for logs; translate by `event` and `key`.

## How the editor uses it (part B, built 2026-10-19)

`src/kuulas/record_session.py` (`RecordSession`, one per open project) and
`src/kuulas/record_take.py` (pure decisions). The editor imports only
`kuulas_recorder.client` (tested: `test_the_editor_uses_only_the_recorders_client`).

- **Connections.** Each command (`devices`, `start`, `stop`, `status`, `repair`) opens
  a short connection of its own. A watcher thread keeps one connection with
  `hello {subscribe, levels}` and pushes what it hears to the page on the live
  channel (`WS /api/live`, frames `{"type": "record", "kind": status | level | notice
  | imported | pending | available}`); the page never polls. With nobody answering it
  retries every 2 s; it never starts a recorder just to look.
- **Starting the recorder.** Only `devices` and `start` call `spawn_supervisor()` when
  nobody answers. When that fails too the answer is `error.record.unavailable` (503) and
  the editor works on.
- **Endpoints.** `GET /api/record/status`, `GET /api/record/devices`,
  `POST /api/record/start` `{device {index,name}, channel, track_id (null: new track),
  name, at}`, `POST /api/record/stop` `{mode, held_ms}`, `POST /api/record/import`
  `{takes}`. Recorder error keys become `error.record.<key>` (`record_take.error_key`);
  events become `record.event.*` notices (`record_take.event_notice`).
- **Stopping** is the page's gesture, a user preference (owner, 2026-10-19): `two_step`
  (default: the first press asks, a second within 4 s stops, otherwise nothing happens),
  `one_click`, or `hold` (2 s). The server refuses a stop without a `mode`, or a hold
  under 2 s, so stray code cannot stop a take (`ui/stop-mode.js`, `record_session.stop`).
- **No listening while recording** (owner, 2026-10-19): starting a take stops playback,
  and play and scrub are refused (`error.record.no_playback`) while any take records.
- **Where a take goes.** Before `start` the editor writes `<take>.editor.json` beside the
  take (the timeline frame, the track or a new track's name). On `stopped` (the event or
  the `stop` answer, whichever comes first; the import is idempotent) each segment of the
  channel becomes one clip at `at + start_frame`, linked in place, on the chosen track or a
  new mono speech track, all in one undo step (`Session.import_take`); several segments are
  one sync group. Take names: `take_names.take_name` over the files in `recordings/`;
  channel names are the track name cut to what the recorder accepts.
- **Crashes.** The editor closing never stops a take; the next editor finds it with
  `hello` and shows the record view again. The recorder dying mid-take (connection lost
  and no answer) is an alarm notice; the editor spawns a new recorder, which repairs the
  take at its start (`recovered`), and the take is offered. On project open any take in
  `recordings/` that no media of the project links to is offered in a notice with one
  Import button, never imported by itself; a sidecar still saying `recording` with no
  recorder writing it is sent to `repair` first (or used as it is when no recorder can
  run: each WAV is valid up to its last flush). The clips of a crashed take are named
  "<take> (interrupted)".
- **The app bundle** carries `src/kuulas_recorder` as a Briefcase source. The recorder
  starts itself and its workers as `<sys.executable> -m kuulas_recorder`; in the app that
  executable is the launcher running `python -m kuulas`, so `kuulas.bundle.main` hands
  `-m kuulas_recorder ...` arguments to the recorder before it opens its log (the
  worker's stdout is its event pipe). `kuulas --selftest` records one second from the fake
  source. Not yet run in a built app.
- **Pre-roll (WP12c).** The record view arms the recorder while it is open in setup
  (`POST /api/record/arm`, repeated every 20 s as the keepalive; `/disarm` when the view
  closes or pre-roll is set to off), as a preference (off, 10, 30, 60 default, 120 s;
  Transport > Pre-roll, `record.preroll`). It shows "Armed: listening, not recording"
  and a level meter before Record. Armed is not recording: playback is not blocked by
  it, the take starts at Record exactly as before, and `Session.import_take` takes an
  optional per-clip head cut for the part before the timeline start.
- **Not in part B:** the take log (`mark`, WP12's log panel), several channels (WP12b).

## Open problems

- Not yet run against a real input device: this Mac has none. Run
  `tests/hardware/test_record.py` on a Mac with an interface, then unplug the
  interface mid-take by hand to see what CoreAudio really does (no callback,
  or `finished_callback`, or an error) and how long a device return takes.
- CoreAudio "default device changed" is not followed: a take stays on the
  device it started with, by name.
- Several takes at once, several devices at once and punch-in are WP12b.
- Windows: named-pipe transport, `SetThreadExecutionState`, WASAPI device
  names; not built. Linux: no sleep inhibit.
- If Python still stalls under measurement on real hardware, the worker can
  be rewritten in Rust or C without changing the protocol or the files.
- The take's start time ignores the host's input latency (a few ms); the
  editor aligns recordings by sound anyway (WP16).
