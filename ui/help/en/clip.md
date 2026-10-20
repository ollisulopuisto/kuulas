---
id: clip
title: A clip
applies-to: [clip]
commands: [edit.split, edit.delete, edit.cut, edit.lift_cut, edit.close_gap_all, clip.mute, clip.quick_mute, clip.fade, edit.undo]
related: [timeline, track, transcript]
---
A clip is a stretch of one recording placed on a track. Several clips can come from the same recording; selecting one marks its siblings with a bracket.

## Edit it
- Split at the play cursor: {key:edit.split}
- Delete: {key:edit.delete}. A soft cut: the audio goes quiet, the gap stays, and the Cuts list can restore it. The clipboard is untouched.
- Cut: {key:edit.cut}. Copies to the clipboard and closes the gap on every track of the sync group.
- Lift-cut: {key:edit.lift_cut}. Copies to the clipboard and soft-deletes in place: the gap stays and can be restored.
- Close the gap on all tracks: {key:edit.close_gap_all}. Ripples the selection or in-out range out of every track; the clipboard is untouched.
- Mute the clip: {key:clip.mute}. Muted clips are drawn faint and hatched.
- Quick mute (lip smacks): {key:clip.quick_mute}. Mutes a short stretch around the play cursor (0.5 s by default, set in Preferences) on all tracks or the selected ones; works while playing. One undo step; nothing is deleted.
- Fade in and out: {key:clip.fade}

Every edit is one step back with {key:edit.undo}.

## Look closer
The inspector shows the clip's level, sync and source. {show:inspector}

See also [[track]] and [[transcript]].
