---
id: bus
title: A bus
applies-to: [bus]
commands: [bus.collapse, bus.expand, bus.role_speech, bus.role_music, bus.role_none, bus.reapply_role, track.match_role, track.mute, track.solo]
related: [track, timeline]
---
A bus groups tracks that are mixed together, such as all the voices or all the music. Its colour runs down the left edge of its tracks as a spine, and its letter badge (A, B …) appears wherever the bus is named.

- Collapse the bus to one row: {key:bus.collapse}. A collapsed bus shows one thin ribbon per track, filled where that track has sound.
- Expand it again: {key:bus.expand}
- The bus's mute and solo act on every track in it; its fader sets the level of the whole bus.

A bus can have a role, speech or music. Choosing it gives every track on the bus that role in one undo step, and a track you move onto the bus follows it:
- Set the role: {key:bus.role_speech}, {key:bus.role_music}, or clear it with {key:bus.role_none}
- A track's Role choice (inspector, or its header menu) is "Match bus role" by default; choose Speech or Music to override it, or {key:track.match_role} to follow the bus again.
- A track that was set by hand to another role than its bus shows a "!" flag, and the bus shows its role with an asterisk and a Reapply button: {key:bus.reapply_role} gives all its tracks the bus role again.

A bus with only one track is merged into that track's header. To put a track on a bus, use the bus picker in its header or the inspector.

See also [[track]].
