---
id: history
title: History
applies-to: [history]
commands: [edit.undo, edit.redo]
related: [clip, timeline]
---
History lists every edit since the project was made, newest at the bottom, with the time it happened. A line marks where each working session began and ended.

- Undo and redo: {key:edit.undo} and {key:edit.redo}
- Go back to any earlier step: select it in the list. Nothing is lost: the steps after it stay in the list and you can return to them.
- Saved versions are pinned in the list.
- Statistics: File, Statistics… (or the command palette) counts this session: runtime, clips, who talked, the number of edits and the time spent editing. Copy it as text or save it as JSON. Undo is not recorded in the history, so it is not counted.

Undo never touches the clipboard. See also [[timeline]].
