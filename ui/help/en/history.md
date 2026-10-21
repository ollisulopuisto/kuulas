---
id: history
title: History
applies-to: [history]
commands: [edit.undo, edit.redo, app.save_named, app.save, history.saved_only, history.rename_version]
related: [clip, timeline]
---
History lists every edit since the project was made, newest at the bottom, with the time it happened. A line marks where each working session began and ended.

- Undo and redo: {key:edit.undo} and {key:edit.redo}
- Go back to any earlier step: select it in the list. Nothing is lost: the steps after it stay in the list and you can return to them.
- Saved versions: {key:app.save_named} (File, Save a named version) names the current step. It is drawn in the list with a bookmark and its name; versions made by sending a copy or exporting carry a small label saying which. Plain {key:app.save} only makes a backup copy and adds nothing to the list.
- Show only saved versions: the "Saved versions" button at the top (or Go to, Show only saved versions in History) hides the ordinary steps. The choice is remembered. The text box beside it filters by words in the step or the version's name, and works together with the button.
- Rename a saved version: pick it, then Go to, Rename the picked saved version. Restore works on a saved version like on any step.
- Statistics: File, Statistics… (or the command palette) counts this session: the session's duration, each track's span, content, muted time and time without mutes, the clip lengths, who talked, the number of edits and the time spent editing. Copy it as text or save it as JSON. Undo is not recorded in the history, so it is not counted.

Undo never touches the clipboard. See also [[timeline]].
