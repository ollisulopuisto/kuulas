---
id: record
title: Recording a take
applies-to: [index]
commands: [transport.record, record.stop_mode, record.preroll, marker.add]
related: [track, timeline]
---
Record one or more input channels onto tracks: {key:transport.record} opens the record view. Choose the input, the channel and the track (or a new one), then press Record. The take starts where the playhead is and appears as a clip there when you stop.

- Pre-roll: you can never press Record too late. While the record view is open the input is listened to and the last 60 seconds are kept in memory; the take starts that far before you pressed Record, and the clip is placed so that the pre-roll ends at the playhead (cut off at the start of the timeline). Choose off, 10, 30, 60 or 120 seconds: {key:record.preroll}, or the Pre-roll setting under More options. The view says "Armed: listening, not recording" while this is on. Nothing is written to disk until you press Record; closing the view, quitting or a crash throws the buffer away.

- Listen to your microphone through your audio interface's direct monitoring. More options can enable playback of the other tracks; use headphones so the microphone does not record them.
- Stopping takes two presses of Stop (or Space) by default: the first asks "Stop recording?", the second, within four seconds, stops. If you do not press again, the take simply goes on. You can choose one click or a 2-second hold instead: {key:record.stop_mode}, or the setting under More options.
- Hiding the record view, closing the window or even a crash of the editor does not stop a take. A red "Recording" chip beside the transport controls brings the view back; reopening the project shows it again.
- The files are plain WAV files in the project's recordings folder, written so that everything up to the last second survives a crash or a pulled cable. A take that a crash interrupted is offered for import the next time you open the project; it is never imported without asking.
- If the input is unplugged, the take waits for it and continues; the gap stays a gap on the timeline. Low disk space is announced at 30, 10 and 2 minutes left.

On a Mac the first recording asks for permission to use the microphone. When kuulas runs from a terminal, it is the terminal that needs the permission (System Settings, Privacy & Security, Microphone). Without it the input is silent: watch the level meter.

See also [[track]].

While a take records, Add marker (or {key:marker.add}) puts a marker where the take is now, not at the play cursor, so you can flag a good answer or a mistake as it happens. The markers stay where they are when the take's clips land.

To record from several devices at once, combine them in macOS first: Audio MIDI Setup > Create Aggregate Device, tick the devices (and Drift Correction for all but the clock device). Kuulas then sees one device with all the channels, and each channel can go to its own track.

While a take records, its tracks are drawn on the timeline as they come in: a bar per pixel with the loudest sample, and a red head where the take is now. New tracks also show the growing waveform before you stop. Live and saved waveforms use the same display preferences. The clips take over from the drawing when you stop.

When you press Record the record view steps aside and the timeline is in front, with the take drawn on its tracks (a new track is made at that moment). The view follows the take while you are watching it and leaves it alone once you scroll away. The recording chip beside Play and Record brings the recording view back; Stop and Add marker are next to it. While a take records, editing is paused (a cut or move before the take would put it in the wrong place); you can scroll, zoom, select, read and add markers.

In the setup, "Clips you play go on" chooses the track for the clips you play from the Clipboard (the cart keys, or a chip's play button) while the take records: a new track called Questions, or any track that is not recorded onto. Each clip you play is also put on that track where the take is at that moment, so the question sits next to the answer. If the track already has audio from the play cursor on, a warning says the clips will overwrite it.

Before recording, input meters check peak level in dBFS. During recording they show a three-second loudness average in LUFS, with −23 and −16 reference marks. Loudness appears once enough recorded audio is available. The clipping warning responds separately to peaks.
