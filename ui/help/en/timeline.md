---
id: timeline
title: The timeline
applies-to: [timeline]
commands: [transport.play, view.toggle, view.fit, view.fit_selection, view.zoom_in, view.zoom_out, view.back, view.wheel_mode, view.clip_words, view.follow, view.show_playhead, view.toggle_sidebar, panel.next, nav.home, spot, time.copy, help.open, help.keys]
related: [clip, track, bus]
---
Every track is a lane, and time runs left to right. A click anywhere in the lanes moves the play cursor there. A click on a clip also selects it; Shift+click adds or removes a clip. Drag across the lanes to mark a time range. While you drag, a hint on the lanes tells which key turns the range into the clips it touches (they are selected and the in and out marks go to their span) and which key cancels.

## Listen
- Play or stop: {key:transport.play}. Space always belongs to the timeline, whichever panel you are in.

## Zoom and move
- Close or wide view: {key:view.toggle} {show:view-toggle}
- Zoom in or out: {key:view.zoom_in} or {key:view.zoom_out}
- Show the whole edit: {key:view.fit}
- Fit the selection or in-out range: {key:view.fit_selection}
- Back to the view before: {key:view.back}

While playing, the view follows the play cursor (the Follow chip in the corner is lit). Scrolling, dragging the overview or zooming turns Follow off and the view stays where you put it; an arrow at the edge then shows where the play cursor is. Click the chip, the arrow or the cursor itself, or start, stop or jump to a time (Home, End, a marker, a transcript word, Spot, Tab to the next stop), to follow again. Nudging the play cursor with the arrow keys or clicking a visible spot on the ruler does not. {run:view.follow} {run:view.show_playhead}

Density, waveform and follow settings are in the View menu. {show:view-menu} So are Fit tracks to the window and Keep tracks fitted to the window. To size one lane, drag the bottom edge of its header; double-click the edge to reset it.

Two-finger scrolling on a trackpad zooms the time axis around the pointer by default; sideways movement scrolls time, and up or down with the shift key held scrolls the lanes (the scrollbar and keys work too). A mouse wheel still scrolls, and scrolling with the command or control key held, like pinching, always zooms. Change it here: {run:view.wheel_mode}

Zoomed in far enough to read them, each speech clip writes its words under its name, so you see which word is where in the waveform. The word under the play cursor is brighter, and words you select in the transcript stand out. {run:view.clip_words}

To give the timeline more width, hide the whole side panel (the x on its tab strip, or here). Opening Help, Auto-Silence options or a side tab shows it again. {run:view.toggle_sidebar}

## How silence looks
- Filled waveform: it sounds. Outline only: it is silent, muted or closed by Auto-Silence; the clip body is darker there.
- A padlock marks a stretch closed by Auto-Silence; a muted clip has none. An open padlock after a clip's name means the clip keeps the mic open.
- Dashed amber lines mark where a closed stretch starts and ends; they are not clip edges and cannot be dragged. Clip edges stay solid, visible and draggable inside a silent stretch.
- A thin rounded outline round several clips marks one group.
- Grey or dimmed lanes are not part of the next operation (View > Lanes outside the operation).
- A clip whose audio file is missing shows a red warning sign and no waveform. Double-click it to locate the file.

## Jump to a time
- Click the big time in the corner to copy it to the clipboard; double-click it, or press {key:spot}, to type a time and jump there. Confirming the field jumps; leaving it cancels.
- Type 1:23.5 (or 83,2) for that time, or start with + or - to move from the play cursor: +100 is 100 seconds on, -30 is 30 back, +1:30 is 90 on, +500ms is half a second. The result stays inside the edit.
- The same works in the In, Out and Length rows: a time sets the mark, +2 or -2 moves it. Alt+click on a row copies its time.

## Panels
{key:panel.next} moves the keyboard to the next panel; {key:nav.home} brings it back here.

## Exporting the selection
Every export exports only what is selected, and says so when it starts ("Exporting the selection only: tracks Anna, Ville, 12.00-18.30").
- With in and out marks (or a range dragged across the lanes): that time range, on the tracks a range command would use.
- With clips selected and no range: the tracks that hold those clips, from the first selected clip's start to the last one's end. Everything on those tracks in that span is included, not only the selected clips.
- With nothing selected: the whole mix.

The export options and the automixer dialog show the selection and a box, "Only export the selection", ticked while there is a selection. Untick it to export everything. The file name carries the span and the tracks, and an existing file is never replaced. Muted tracks stay muted, and solo works as in the whole mix.

## Stepping back
{key:nav.home} undoes one thing per press, the newest first, and then puts the keyboard on the timeline:
- an Auto-Silence preview (dropped, nothing was applied)
- the text field you are typing in
- the selected track headers
- the selected clips, the dragged range and the in and out marks, together
- focus mode
- then it only moves the keyboard here

In the transcript a selected word range goes first; in the Clipboard filter the typed text goes first. A drag in progress, a menu or a dialog is closed before any of this. {key:nav.home} never stops playback ({key:transport.play} does) and never cancels an export or automix: use the Cancel button on its notice.

## Keys that cannot act
An editing key (cut, delete, split, mute, copy and the rest) that has nothing to work on says why in a one-line notice and never beeps. The editing keys work from every panel except while you type or a dialog is open; after one works from a side panel, the keyboard returns to the timeline.

## Help
{key:help.open} opens help for what you are looking at; {key:help.keys} lists every key.

See also [[clip]] and [[track]].

While you move a clip, hold Cmd (Ctrl on Windows and Linux) to make its edges snap to the volume automation too: the ends of a ducking ramp (a level change of 3 dB or more), the level changes of other clips' envelopes and the edges of the stretches Auto-Silence closed. Small marks along the top of the lanes show where; let go of the key and they go away. Alt still turns snapping off, Shift still moves in fine steps.
