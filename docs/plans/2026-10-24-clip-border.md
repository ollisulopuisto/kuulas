# Clip Border Contrast Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Separate 1 px clip borders from every waveform and both file body tones in light and dark themes.

**Architecture:** Keep the existing `theme.clipEdge` rendering path and change semantic token references only. Test resolved colours using WCAG relative luminance, without changing selection, silence, gate or group rendering.

**Tech Stack:** CSS semantic tokens, Node test runner, existing offline prototype sync script.

### Task 1: Measure before changing colours

1. Extend `ui/tests/tokens.test.js` with a pure test for every track hue in both themes: border/wave >= 1.6 and border/body (including body-alt) >= 1.5. These are separation floors between adjacent graphics; existing waveform/body accessibility tests remain stronger.
2. Also check the border differs from selection, gate and group colours.
3. Run `node --test --test-name-pattern='clip border' ui/tests/tokens.test.js`; expect contrast failures with the current tokens.

### Task 2: Fix the semantic colours

1. Update `--signal-clip-edge` in `ui/tokens.css` using existing neutral primitives, including both dark theme blocks. Keep the waveform and 1 px rendering unchanged.
2. Run the focused test until all palette pairs meet the floors.
3. Update the border rules and measured minima in `docs/design/SILENCE-VISUALS.md`.
4. Run `node docs/design/sync-tokens.mjs` to refresh `docs/design/prototype/index.html`.

### Task 3: Verify and deliver

1. Run `node --test ui/tests/tokens.test.js` alone, then `node --test ui/tests/`.
2. Run `uv run --offline ruff check .`. C6 explicitly delegates Biome to the coordinator.
3. Review `git diff --check` and the final diff, then commit locally on `codex-c6-clip-border` with the required Codex attribution.
4. Report test counts and that the appearance on a real screen remains unverified.
