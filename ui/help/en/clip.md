---
id: clip
title: A clip
applies-to: [clip]
commands: [edit.split, edit.delete, edit.cut, edit.lift_cut, edit.close_gap_all, edit.paste, edit.paste_insert, clip.mute, clip.quick_mute, clip.fade, clip.relink_media, edit.undo]
related: [timeline, track, transcript]
---
A clip is a stretch of one recording placed on a track. Several clips can come from the same recording; selecting one marks its siblings with a bracket.

## Edit it
- Split at the play cursor: {key:edit.split}
- Delete: {key:edit.delete}. A soft cut: the audio goes quiet, the gap stays, and the Cuts list can restore it. The clipboard is untouched.
- Cut: {key:edit.cut}. Copies to the clipboard and closes the gap on every track of the sync group.
- Lift-cut: {key:edit.lift_cut}. Copies to the clipboard and soft-deletes in place: the gap stays and can be restored.
- Close the gap on all tracks: {key:edit.close_gap_all}. Ripples the selection or in-out range out of every track; the clipboard is untouched.
- Mute the clip: {key:clip.mute}. A muted clip keeps its colour but its waveform loses its fill: only the outline shows, so you still see what is silenced.
- Quick mute (lip smacks): {key:clip.quick_mute}. Mutes a short stretch around the play cursor (0.5 s by default, set in Preferences) on all tracks or the selected ones; works while playing. One undo step; nothing is deleted.
- Edited the recording in another program (say, removed noise)? **Locate / Relink media…** in the clip's menu points every clip of that recording at the file you choose, after showing both lengths; one undo step, and neither file is changed. A clip whose file is missing shows a red warning sign; double-click it to locate the file.
- Fade in and out: {key:clip.fade}

## Range or clips: the latest choice wins
When you have both an In-Out range and selected clips, Delete, Cut, Lift-cut, Close the gap and Copy act on whichever you touched last. Select clips after you set In and Out, and the next edit touches those clips (the status bar says so: "touch the 3 selected clips") and the marks stay but fade. Set or move In or Out, or drag a new range, and the range is the target again ("range 0:12-0:18 on all 4 tracks"). Clearing the selection or the marks leaves the other one. Looping, playing the selection and Export still use the marks first. Undo and Redo do not change the choice.

Every edit is one step back with {key:edit.undo}.

## Paste
- Paste: {key:edit.paste}. Pastes at the play cursor, on the track you have selected, over what is there: clips under the pasted ones are trimmed, split or removed, and nothing later moves. One undo step; recordings are never touched.
- Paste and insert: {key:edit.paste_insert}. Pushes later material along instead of overwriting.
- With In and Out marked, the paste starts at In and is cut at Out if it is longer; a shorter clip keeps its own length. A copy of several clips keeps its layout and every clip is cut at Out.
- The target track is the one whose header is selected (with several selected, the topmost), else the focused track. A copy of several tracks keeps its layout: its first track goes on that track, the others below it.
- With no track selected or focused, the paste goes back to the track it was copied from if it still exists, else to track 1.
- Every paste form (overwrite, insert, on the current track, on the same tracks) follows this rule; only "same tracks" always uses the source tracks. A speech clip can be pasted on a music track.

## Look closer
The inspector shows the clip's level, sync and source. {show:inspector}

A clip that keeps the mic open shows a "Mic kept open" row under Level; its button lets Auto-Silence gate the clip again (the same as Keep the mic open under the selected clips, in the Clip menu).

See also [[track]] and [[transcript]].
