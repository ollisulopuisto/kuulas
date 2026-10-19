---
id: record
title: Recording a take
applies-to: [index]
commands: [transport.record, record.stop_mode]
related: [track, timeline]
---
Record one input channel onto a track: {key:transport.record} opens the record view. Choose the input, the channel and the track (or a new one), then press Record. The take starts where the playhead is and appears as a clip there when you stop.

- kuulas plays nothing while it records. Listen through your audio interface's own direct monitoring.
- Stopping takes two presses of Stop (or Space) by default: the first asks "Stop recording?", the second, within four seconds, stops. If you do not press again, the take simply goes on. You can choose one click or a 2-second hold instead: {key:record.stop_mode}, or the setting at the bottom of the record view.
- Hiding the record view, closing the window or even a crash of the editor does not stop a take. A red "Recording" chip in the toolbar brings the view back; reopening the project shows it again.
- The files are plain WAV files in the project's recordings folder, written so that everything up to the last second survives a crash or a pulled cable. A take that a crash interrupted is offered for import the next time you open the project; it is never imported without asking.
- If the input is unplugged, the take waits for it and continues; the gap stays a gap on the timeline. Low disk space is announced at 30, 10 and 2 minutes left.

On a Mac the first recording asks for permission to use the microphone. When kuulas runs from a terminal, it is the terminal that needs the permission (System Settings, Privacy & Security, Microphone). Without it the input is silent: watch the level meter.

See also [[track]].
