# WP10 Inspector Processed Toggle Implementation Plan

> **For Codex:** Follow this plan with red-green TDD and keep the DSP in `speechmix`.

**Goal:** Let the Inspector switch one selected clip between its source media and its saved voice-chain variant through the existing undoable operation.

**Architecture:** Resolve the selected clip's source and `voice chain` variant from project media. Show an accessible checkbox only when both are present, reflect the clip's current media, and send `use_variant` through the editor when it changes. Add English and Finnish labels in the locale catalogs.

**Tech Stack:** Browser UI JavaScript, existing editor operation API, Node test runner, locale JSON catalogs.

---

### Task 1: Inspector integration

**Files:**
- Modify: `ui/inspector.js`
- Test: `ui/tests/inspector.test.js`
- Modify: `src/kuulas/locales/en.json`
- Modify: `src/kuulas/locales/fi.json`

1. Add a failing Inspector test that confirms no toggle appears without a voice-chain variant.
2. Extend it to verify a source clip shows an unchecked Processed toggle, checking it sends one `use_variant` edit for that clip, and a processed clip shows it checked and can switch back to its source.
3. Run `node --test ui/tests/inspector.test.js` and confirm the new assertion fails because the toggle is missing.
4. Add a small media-pair resolver and render the localized, accessible toggle only when both source and variant are present. Derive its target from the latest Inspector state and rebuild when the clip media or available variant changes.
5. Run the Inspector test file and the full Node UI suite; run Biome on `ui/`.

### Task 2: Integration checks

1. Run `uv run pytest -q` and `uv run ruff check .` as required by the repository instructions.
2. Review the diff, commit the WP10 UI slice locally, and leave version, changelog, roadmap and WP status updates for the integrator.
