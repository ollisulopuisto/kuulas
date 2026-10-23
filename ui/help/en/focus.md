---
id: focus
title: Focus mode
applies-to: [focus]
commands: [view.focus, view.focus_solo, view.focus_shrink, view.focus_hide_others, track.prev, track.next, nav.home]
related: [track, timeline, transcript]
---
Focus mode gives one speaker the room. The current track and every other track of the same speaker grow; the other tracks shrink, but only to a readable size (they share about 40 % of the room, at most 64 px each, and never less than a thin strip when there are very many), so you still see their name, their waveform and their clip edges and the sync at a glance. Focus changes what you see; solo changes what you hear.

- Focus on the current track: {key:view.focus}. Press it again, or {key:nav.home}, to leave. {key:nav.home} first clears a selection or the in and out marks, then leaves focus.
- Focus and solo: {key:view.focus_solo}. Leaving focus brings back the solo settings you had before.
- {key:track.prev} and {key:track.next} move the focus to the previous or next speaker. A click on a strip focuses that track.
- The other tracks are greyed out like lanes outside an operation (View > Lanes outside the operation).
- The lanes change size quickly, without animation while playing or when Animation is off.

In the transcript, what the other speakers say is dimmed so the conversation still reads. To hide their words instead: {run:view.focus_hide_others}

To keep the lane sizes and only grey out the other tracks: {run:view.focus_shrink}

All of these are in View > Focus mode. Focus is part of the view only: it is not saved in the project and not in the undo history.
