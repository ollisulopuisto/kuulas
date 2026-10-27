# Orukeet GUI setup implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Install or select local Orukeet from the editor, align transcription actions, and expose fast listening in the transport corner.

**Architecture:** Download a pinned MLX conversion into a private staging directory, verify every size/hash, publish atomically and remember the selected model per user. Reuse the shared podcast transcription CLI and existing Jobs progress/cancel infrastructure; no DSP or conversion code is copied. The setup dialog offers installation and selection before local transcription and through a menu command. File names, status and compact action buttons share stable grid columns.

**Tech Stack:** Python/FastAPI/urllib/SHA-256; browser modules/native folder dialog; existing Jobs, preferences and command registry.

---

### Task 1: Verified model installation and selection

Files: create `src/kuulas/local_models.py`, `tests/test_local_models.py`; modify `src/kuulas/transcribe.py` and bilingual catalogs.

1. Write tests for successful verified installation, missing model, selecting an existing folder, interrupted/failed/corrupt download, preserving the old setting, and safe default versus legacy resolution.
2. Run `uv run pytest -q tests/test_local_models.py`: initially fails because the module is absent.
3. Implement fixed repository/revision/file manifest, streamed bounded downloads and cooperative cancellation. Publish only after validation; never overwrite any existing model. Use `write_json_atomic` for the per-user setting.
4. Resolve default local transcription through this setting while retaining existing legacy model paths.
5. Run focused tests and Ruff.

Pinned conversion: `itsreidar/orukeet-mlx`, revision `17894066e1d148997bfc93a4d41c605ca1b0475d`.
Source: https://huggingface.co/itsreidar/orukeet-mlx
The conversion's author documents format-only conversion from Orukeet, with original attribution and CC-BY-SA-4.0 weight license. Preserve the license/notice/citation files. The existing shared Parakeet MLX loader consumes its config/model layout; actual inference must verify compatibility before release.

### Task 2: API and GUI

Files: `src/kuulas/server.py`, `desktop.py`, `ui/api.js`, new `ui/orukeet-dialog.js`, command/menu/keymap files, `ui/app.js`, `ui/transcript.js`; API and model tests.

1. Test status, queued install with progress/cancellation, bad selection and persisted selection; run red.
2. Add GET model status, POST install (existing Jobs), POST select. Native folder chooser; browser path input.
3. Add keyboard/menu/palette-accessible Orukeet setup and a dialog with download size/source, progress, cancellation, retry and existing-folder selection.
4. Gate local transcript actions on setup readiness. After install/selection, continue the requested transcription without asking for terminal commands.
5. Shorten action labels and put cloud-transfer explanation outside the buttons. Shared column grid for filename/status/actions, responsive stacking only at narrow widths.

### Task 3: Fast listening button and acceptance

Files: `ui/index.html`, `ui/app.js`, `ui/style.css`, pure transport UI model/tests as needed.

1. Test the button's off/on and exact-speed model against the existing fast state; run red.
2. Add a persistent `transport.speed` button beside playback controls. Preserve the speed slider/chip drag behavior and remappable shortcut hints.
3. Browser acceptance: missing-model setup, install progress/failure/retry, existing model selection, stable transcription rows with long Finnish names, keyboard access, and fast-button/period parity at 1280/1600 px.
4. Run full Python/UI tests and Ruff/Biome before commit. Document actual checks and limits. Publish a new DMG after release validation.

## Implementation validation

- Verified the exact public file manifest against the pinned Hub revision. A real
  install downloaded all 1,254,965,437 bytes into an isolated temporary folder;
  every size/hash matched. The public converted model then transcribed the system-
  generated Finnish test sentence with all six words and word times through the
  existing podcast CLI. No user audio or active model setting was used or changed.
- Failure/cancellation/hash/truncation/space tests preserve the selected old model.
  Legacy faster-whisper job errors now translate to GUI Orukeet setup guidance.
- Chrome acceptance exercised download progress, failure/retry, cancellation,
  invalid/existing-folder selection and automatic continuation of transcription.
  The network transitions in this UI test are simulated; actual transfer/inference
  were checked separately above.
- Chrome reproduced the original misaligned offer columns, then verified common
  action positions and fitting short labels. Clicking the persistent fast button
  and pressing period toggle the same selected-speed state.

The DMG also copies pinned uv/uvx 0.13.6 into Resources/bin before signing,
with MIT/Apache license texts. Packaged selftests require both exact bundled
executables to answer --version under Finder's minimal PATH, preventing a
developer-machine uv installation from masking a missing runtime.

Owner clarification: retain the visible graphical meter at rest and in playback.
Only its measurement/scale changes to three-second LUFS with -23/-16 reference
marks; the peak-clipping warning stays separate. A regression first reproduced
the disappearing meter, then verified persistent bars and LUFS-driven movement.

Ultra is deferred at the owner's request so this release can use the already
published shared podcast tool. The exploratory Ultra changes were saved outside
the worktree in /private/tmp/kuulas27.2-with-deferred-ultra.patch. No Ultra labels
or claims are shipped in this release.

The release pins the published podcast source and external transcription tool
to 7793c0c1b276e90e466cea6d0b09e20fca08c968. An exact-runtime smoke test
first exposed missing lxml in the public CLI's optional local dependency set;
the adapter now supplies it alongside parakeet-mlx in the isolated environment.
A regression reproduced that omission, then passed; the exact public revision
transcribed all six synthetic Finnish words with timestamps using the selected
GUI-installed model. This does not use the concurrent uncommitted Ultra draft.

Final validation: 5,192 Python tests passed (one upstream Starlette deprecation
warning), 3,596 UI tests passed, Ruff and Biome clean. Shell syntax and diff
whitespace checks passed. The exact published-runtime synthetic transcription
and the Chrome acceptance checks described above also passed.
