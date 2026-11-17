# Panel number shortcuts

Clipboard is an independent sidebar tab. Order and Cmd/Ctrl shortcuts are Inspector 1,
History 2, Markers 3, Clipboard 4, Material 5 and Candidates 6. Material contains recordings
only. Former saved Material/Clipboard views restore to Clipboard; all other destinations
remain unchanged. Narrow tab strips can scroll horizontally rather than hide destinations.

In Markers, plain 1–9 jump to point markers in current chronological order (ties by ID),
without moving keyboard focus. Only point markers get numbers; chapters, regions, In/Out,
the automatic left-off row and ruler flags do not. Numbers change when time order changes.
In Clipboard, plain 1–7 play the existing assigned cart slots. Alt+1–7 still play from any
non-text panel, and Shift+Alt+1–7 still assign. There is no Shift+digit global marker jump.
Timeline 1/2 remain Go to In/Out. Text inputs, selects, rename fields and editable content
retain normal typing. Physical digit-key matching preserves Finnish keyboard behavior.

Validation starts with failing regressions for tab order, saved-view migration, chronological
marker numbering and jump behavior. UI dispatch tests cover all three digit contexts,
text fields, modifier isolation and both platform mappings. Full UI tests, lint, focused
Python locale/docs/page tests and synthetic before/after screenshots accompany the PR.
No project format or dependency changes. A native macOS listening check remains untested.
