# Inspector track level readouts, 29 October 2026

Owner: Kuulas UI lane, isolated `fix/inspector-readonly-levels`.

User chose read-only gain and pan in the inspector, leaving graphical controls
and exact numeric entry on the track panel. This changes only the Track section:
clip gain/pan and bus controls are separate existing scopes and stay unchanged.

Track output values read the same current project state and locale formatters.
They have no editing handlers and create no history steps. Track panel numeric
editing already works by double-clicking its value or pressing Enter on the
focused slider; Enter/blur applies and Escape cancels. No replacement widgets
or audio/model changes are needed.

Compact headers under 40px hide gain/pan; users can expand the lane by dragging
its bottom edge, or double-click that edge to reset its size. This existing
access route remains. No new compact widgets are added.

Tests: new red/green regression proves outputs have no numeric input or editing
handlers, reflect changed shared state and emit no edit. All 3629 Node tests pass.
Native Mac acceptance remains separate. No changes overlap Viewer, performance,
Codex backups/range-history or recording meter work.
