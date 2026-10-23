---
id: record
title: Recording a take
applies-to: [index]
commands: [transport.record, record.stop_mode, record.preroll, marker.add]
related: [track, timeline]
---
Record one input channel onto a track: {key:transport.record} opens the record view. Choose the input, the channel and the track (or a new one), then press Record. The take starts where the playhead is and appears as a clip there when you stop.

- Pre-roll: you can never press Record too late. While the record view is open the input is listened to and the last 60 seconds are kept in memory; the take starts that far before you pressed Record, and the clip is placed so that the pre-roll ends at the playhead (cut off at the start of the timeline). Choose off, 10, 30, 60 or 120 seconds: {key:record.preroll}, or the Pre-roll setting in the record view. The view says "Armed: listening, not recording" while this is on. Nothing is written to disk until you press Record; closing the view, quitting or a crash throws the buffer away.

- kuulas plays nothing while it records. Listen through your audio interface's own direct monitoring.
- Stopping takes two presses of Stop (or Space) by default: the first asks "Stop recording?", the second, within four seconds, stops. If you do not press again, the take simply goes on. You can choose one click or a 2-second hold instead: {key:record.stop_mode}, or the setting at the bottom of the record view.
- Hiding the record view, closing the window or even a crash of the editor does not stop a take. A red "Recording" chip in the toolbar brings the view back; reopening the project shows it again.
- The files are plain WAV files in the project's recordings folder, written so that everything up to the last second survives a crash or a pulled cable. A take that a crash interrupted is offered for import the next time you open the project; it is never imported without asking.
- If the input is unplugged, the take waits for it and continues; the gap stays a gap on the timeline. Low disk space is announced at 30, 10 and 2 minutes left.

On a Mac the first recording asks for permission to use the microphone. When kuulas runs from a terminal, it is the terminal that needs the permission (System Settings, Privacy & Security, Microphone). Without it the input is silent: watch the level meter.

See also [[track]].

While a take records, Add marker (or {key:marker.add}) puts a marker where the take is now, not at the play cursor, so you can flag a good answer or a mistake as it happens. The markers stay where they are when the take's clips land.
