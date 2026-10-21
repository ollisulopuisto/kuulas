---
id: timeline
title: The timeline
applies-to: [timeline]
commands: [transport.play, view.toggle, view.fit, view.fit_selection, view.zoom_in, view.zoom_out, view.back, view.wheel_mode, view.clip_words, view.toggle_sidebar, panel.next, nav.home, spot, time.copy, help.open, help.keys]
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

Density, waveform and follow settings are in the View menu. {show:view-menu} So are Fit tracks to the window and Keep tracks fitted to the window. To size one lane, drag the bottom edge of its header; double-click the edge to reset it.

Two-finger scrolling on a trackpad zooms the time axis around the pointer by default; sideways movement scrolls time, and up or down with the shift key held scrolls the lanes (the scrollbar and keys work too). A mouse wheel still scrolls, and scrolling with the command or control key held, like pinching, always zooms. Change it here: {run:view.wheel_mode}

Zoomed in far enough to read them, each speech clip writes its words under its name, so you see which word is where in the waveform. The word under the play cursor is brighter, and words you select in the transcript stand out. {run:view.clip_words}

To give the timeline more width, hide the whole side panel (the x on its tab strip, or here). Opening Help, Auto-Silence options or a side tab shows it again. {run:view.toggle_sidebar}

## How silence looks
- Filled waveform: it sounds. Outline only: it is silent, muted or closed by Auto-Silence; the clip body is a little darker there.
- A padlock marks a stretch closed by Auto-Silence; a muted clip has none. An open padlock after a clip's name means the clip keeps the mic open.
- Clip edges stay visible and draggable inside a silent stretch.
- Grey or dimmed lanes are not part of the next operation (View > Lanes outside the operation).
- A clip whose audio file is missing shows a red warning sign and no waveform. Double-click it to locate the file.

## Jump to a time
- Click the big time in the corner to copy it to the clipboard; double-click it, or press {key:spot}, to type a time and jump there. Confirming the field jumps; leaving it cancels.
- Type 1:23.5 (or 83,2) for that time, or start with + or - to move from the play cursor: +100 is 100 seconds on, -30 is 30 back, +1:30 is 90 on, +500ms is half a second. The result stays inside the edit.
- The same works in the In, Out and Length rows: a time sets the mark, +2 or -2 moves it. Alt+click on a row copies its time.

## Panels
{key:panel.next} moves the keyboard to the next panel; {key:nav.home} brings it back here.

## Help
{key:help.open} opens help for what you are looking at; {key:help.keys} lists every key.

See also [[clip]] and [[track]].
