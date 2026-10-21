---
id: history
title: History
applies-to: [history]
commands: [edit.undo, edit.redo, history.restore, history.goto_restore_point, history.expand_all, app.save_named, app.save, history.saved_only, history.open_saved, history.rename_version]
related: [clip, timeline]
---
History lists every edit since the project was made, newest at the top, with the time it happened. A line marks where each working session began and ended. Each step is named after what it did and to what ("Track settings: Olli · gain −3.0 dB", "Split: Anna at 12:34.5"), in the language you use now. Several steps in a row on the same thing show as one row ("×4"); the right arrow shows each.

- Undo and redo: {key:edit.undo} and {key:edit.redo}
- Go back to any earlier step: select it, then Restore (the button, {key:history.restore}, or a double click). Selecting alone changes nothing. Restore adds a new step equal to the one you picked, so nothing is lost: the state you left is one Undo away and every step stays in the list. It goes back in the edit only; media and sync are not rewound.
- After a Restore the new step reads "Restored to: …", the step it went back to carries a "restore point" tag, and a bracket in the left margin joins the two. The steps it skipped fold into one "↩ Rolled back N steps" row. {key:history.goto_restore_point} on a restore row jumps to its restore point.
- Steps you have undone sit above the current one in an open "↶ Undone" group (Redo brings them back). An edit after an undo leaves the undone steps on a side path: a closed "⑂ Left behind" group. Each kind has its own icon and word; all of them can still be restored.
- Groups: the right arrow opens one, the left arrow closes it, and {key:history.restore} on a group row does either. Go to, Expand all groups in History opens every group at once; again puts them back.
- Saved versions: {key:app.save_named} (File, Save a named version) names the current step. It is drawn in the list with a bookmark and its name; versions made by sending a copy or exporting carry a small label saying which. Plain {key:app.save} only makes a backup copy and adds nothing to the list.
- Show only saved versions: the switch at the top has two states, "All steps" and "Saved versions" (or Go to, Show only saved versions in History); "Saved versions" hides the ordinary steps. A line under it reminds you that any step can be restored, with a link back to All steps. Go to, Open History at the saved versions opens the tab with this filter on. Each version says where it stands: in the current state, undone, rolled back or left behind. The choice is remembered. The text box beside it filters by words in the step or the version's name, and works together with the button.
- Rename a saved version: pick it, then Go to, Rename the picked saved version. Restore works on a saved version like on any step.
- Statistics: File, Statistics… (or the command palette) counts this session: the session's duration, each track's span, content, muted time and time without mutes, the clip lengths, who talked, the number of edits and the time spent editing. Copy it as text or save it as JSON. Undo is not recorded in the history, so it is not counted.

Undo never touches the clipboard. See also [[timeline]].
