# Track Header Tab and Hover Slab Implementation Plan

> **Implementation note:** Execute this plan in the `codex/track-header-tab-redesign` worktree, one task at a time, with UI tests failing before the matching implementation.

**Goal:** Finish the track-header redesign on top of the existing compact flyout by making the resting header read as a compact tab, keeping its control slab over the timeline, and compacting bus controls.

**Architecture:** Keep the current body-level fixed flyout and reducer-driven hover/focus/pin state. Change only the track header and bus presentation, with CSS geometry tests guarding the stable timeline origin and localized existing labels preserving accessibility.

**Tech Stack:** Browser UI in `ui/tracks.js` and `ui/style.css`; Node's built-in test runner; Biome 2.2.4; existing real-editor screenshot workflow.

---

## Goal

Replace the wide per-track header controls with a compact downward-pointing tab
showing the track name and M/S state. Keep the timeline visible behind the
former header area. Hover, keyboard focus, or explicit activation reveals the
full control slab downward as an overlay without moving the waveform. Delay
closing while the pointer travels from the tab to the controls, and allow the
slab to stay pinned. Keep bus controls compact and use a rotary pan control.

## Scope

- Implement the tab, overlay slab, hover/focus/activation behavior and pinning.
- Preserve reliable pointer targets and track actions in compact layouts.
- Reduce bus header height and render bus pan as a rotary encoder.
- Hide gain envelopes on muted and auto-silenced clip regions; dim those
  regions further while keeping clip labels readable at small heights.
- Update UI regression coverage, user documentation and README screenshots.
- Update release notes/version only at integration, then publish a notarized
  GitHub release after CI completes.

## Implementation sequence

1. Inspect the current track/header DOM, layout and screenshot workflow.
2. Add or update UI regression tests first for collapsed/expanded layout,
   overlay geometry, delayed close, focus/pinning, compact-height labels, bus
   controls and hidden gain envelopes.
3. Implement the smallest CSS/JS changes that satisfy those tests and keep all
   user-facing text localized.
4. Update README and capture genuine UI screenshots of collapsed and expanded
   states.
5. Run required project checks, integrate to main, push, tag and monitor the
   notarized DMG workflow through artifact/release availability.

## Bite-sized execution tasks

### Task 1: Lock the remaining presentation requirements

**Files:**
- Modify: `ui/tests/track-control-layout.test.js`
- Modify: `ui/tests/track-header-flyout.test.js`

Add regressions for the downward tab shape, unchanged track-header column and
timeline origin while the flyout is open, and a rotary pan control on bus
headers. Keep existing hover, focus, pin, Escape, and close-delay behavior
covered; the current flyout implementation already provides those behaviors.

Run `node --test ui/tests/track-control-layout.test.js ui/tests/track-header-flyout.test.js`
and confirm the new presentation assertions fail before changing CSS or UI code.

### Task 2: Apply the track tab and compact bus controls

**Files:**
- Modify: `ui/tracks.js`
- Modify: `ui/style.css`
- Modify: `ui/tests/track-control-layout.test.js`

Style the stable name/M/S row as the tab, keep the controls in the existing
fixed flyout, compact the bus header, and make bus pan use the existing rotary
slider treatment. Do not add new user-facing copy; reuse localized labels.

Run the focused Node tests from Task 1 and Biome on `ui/`.

### Task 3: Verify compact-height and inactive-envelope behavior

**Files:**
- Modify: `ui/tests/track-control-layout.test.js` only if a missing regression
  is found; otherwise no code change.

Run `node --test ui/tests/lanes.test.js ui/tests/track-control-layout.test.js`
to confirm compact labels and hidden muted/Auto-Silence envelope targets stay
intact.

### Task 4: Capture and document the real editor states

**Files:**
- Modify: `README.md`
- Add: `docs/design/screenshots/app-track-header-collapsed.png`
- Add: `docs/design/screenshots/app-track-header-expanded.png`

Capture screenshots from the running editor in a real browser window, one with
the tab collapsed and one with its flyout open. Do not substitute prototype or
headless screenshots for these two acceptance images. The owner needs the
screen for other work now; defer these captures until the owner says the screen
is available. Do not start the app to take them in the meantime.

### Task 5: Verify and hand off

Run `node --test ui/tests/`, `npx --yes @biomejs/biome@2.2.4 check ui/`,
`uv run pytest -q`, and `uv run ruff check .`. Commit the completed work, push
the feature branch, and open or update its pull request. Release versioning and
notarized DMG publication remain integration work.

## Acceptance

- Expanding/collapsing never changes waveform position or width.
- The collapsed tab exposes track name and M/S state; the expanded slab
  provides the existing controls and remains reachable by pointer/keyboard.
- Bus header is compact and bus pan is rotary.
- Muted and auto-silenced clips show no gain envelope and read as inactive.
- README screenshots show both states and are captured from the app.
- CI and the tagged notarized DMG workflow succeed.
