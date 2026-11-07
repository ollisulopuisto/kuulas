# WP8 History Hover Preview Implementation Plan

> **Implementation note:** Use `/private/tmp/kuulas-wp8-history-hover-preview` on branch `codex/wp8-history-hover-preview`. Write regression tests before the matching implementation. Keep the editor closed while the owner needs the screen.

**Goal:** Preview any history step as read-only ghost clip outlines on the timeline while its history row is hovered or keyboard-focused.

**Architecture:** Reuse `History.project_at(node)` to read a step in the current edit without moving its head. Return only track IDs and clip timeline ranges from the API, calculate visible overlay rectangles in a pure UI module, and draw dashed ghost outlines on the existing timeline overlay. History row hover/focus controls the preview with request tokens so a slow response cannot replace a newer choice; leaving the row or history panel clears it.

**Tech Stack:** Python 3.13 / FastAPI session API, browser UI modules, Node's built-in test runner, pytest, Biome 2.2.4, Ruff.

---

## Scope

- Show the historical clip arrangement as outlines over the current timeline.
- Support pointer hover and keyboard focus on history rows.
- Clear the preview when the pointer/focus leaves history, the history tab closes, or a newer request wins.
- Keep the current project, history head, selection, and transport unchanged.
- Bound work to visible timeline rows and the visible horizontal range.

## Tasks

### Task 1: Define the read-only preview response

**Files:**
- Test: `tests/test_server.py`
- Modify: `src/kuulas/session.py`
- Modify: `src/kuulas/server.py`

**Step 1:** Add a session test that requests an older node and gets only `{track, clip, start, end}` geometry; assert the active head, state, and material head do not move. Add a test that a node from another edit is rejected.

**Step 2:** Run the tests and confirm they fail because the session/API method is absent.

**Step 3:** Add a read-only `Session.history_preview(node)` method using the current `History.project_at(node)` and a `GET /api/history/{node}/preview` route. Serialize only clip geometry.

**Step 4:** Run the focused tests and verify both pass.

### Task 2: Calculate visible preview boxes

**Files:**
- Create: `ui/history-preview.js`
- Create: `ui/tests/history-preview.test.js`

**Step 1:** Test that preview clips map to the same timeline rows and x coordinates as current clips, are clipped to the viewport, and ignore missing or offscreen tracks/clips.

**Step 2:** Run the tests and confirm the new module is missing.

**Step 3:** Implement a pure geometry helper that only visits visible track rows and clips intersecting `[scroll, scroll + viewportFrames)`.

**Step 4:** Run the focused Node test file.

### Task 3: Connect history row hover and keyboard focus

**Files:**
- Modify: `ui/api.js`
- Modify: `ui/history-panel.js`
- Modify: `ui/store.js`
- Modify: `ui/tests/history-panel.test.js`

**Step 1:** Add tests for pointer enter, focus, leave, panel close, and two out-of-order preview responses. Assert preview changes do not call restore or edit actions.

**Step 2:** Run the focused UI tests and confirm the assertions fail.

**Step 3:** Fetch the preview by node, ignore stale responses with a monotonically increasing request token, store only the current preview geometry, and clear it when hover/focus context ends or the History tab closes.

**Step 4:** Run `node --test ui/tests/history-panel.test.js ui/tests/history-preview.test.js`.

### Task 4: Draw the ghost outlines

**Files:**
- Modify: `ui/timeline.js`
- Modify: `ui/tests/history-preview.test.js`

**Step 1:** Add a regression for dashed preview outlines being derived from the current viewport and track layout.

**Step 2:** Confirm the assertion fails before drawing is added.

**Step 3:** Draw the outlines on the existing overlay with a quiet theme colour, no waveform fetches, and no pointer interaction; leave clip bodies and the playhead visible beneath/above them.

**Step 4:** Run all UI tests and Biome.

### Task 5: Verify and hand off

Run:
- `node --test ui/tests/`
- `npx --yes @biomejs/biome@2.2.4 check ui/`
- `uv run pytest -q`
- `uv run ruff check .`

Commit the feature branch, push it, and open a draft PR with the test results and any owner-only visual check still pending. Do not start the app or capture screenshots until the owner says the screen is available.

## Acceptance

- Hovering or keyboard-focusing a history row shows that step's clip arrangement as ghost outlines.
- Leaving history or focusing another step clears/replaces the overlay; stale responses cannot win.
- Preview is read-only: project state, history head, selection, transport, and material remain unchanged.
- Only visible tracks and clip ranges are drawn; no waveform or media work is started.
