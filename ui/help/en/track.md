---
id: track
title: A track
applies-to: [track]
commands: [track.mute, track.solo, rename, app.duck_music, app.auto_silence_options, transport.play]
related: [bus, clip, timeline]
---
A track holds the clips of one voice or one kind of sound. Its header, on the left of the lane, names it and shows its colour; the controls appear when the track is current or under the pointer. {show:track-headers}

- Mute or solo: {key:track.mute} and {key:track.solo}, or the M and S buttons.
- Rename: {key:rename}
- Level and pan: the header's sliders, or the inspector.
- Duck music under speech from Track > Auto; choose which music tracks take part in the inspector.
- Choose **Fade in the gaps** to raise music during longer pauses, or **Duck under speech** to lower it continuously while people speak. The sidechain style lets you adjust depth, threshold, attack and release.
- Auto-Silence closes each speech mic where its owner is not talking. **Auto-Silence options…** (Track > Auto) opens a panel beside the timeline: move the sliders and each lane shows, hatched and marked *preview*, what would be closed; **Listen** (or {key:transport.play}) plays it that way. Nothing changes until **Accept**, one undo step; **Close** leaves the project as it was. The first open measures the speech once, which takes a while on a long project.
- Move the current track with the arrow keys up and down.

The coloured pill is the speaker; the rail on the far left, if there is one, is the track's [[bus|bus]].
