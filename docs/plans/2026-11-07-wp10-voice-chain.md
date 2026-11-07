# WP10 Voice Chain Variants Implementation Plan

> **For Codex:** Implement this plan task-by-task with red-green TDD. Keep the DSP in `speechmix`; Kuulas owns project media, jobs, and undoable clip selection.

**Goal:** Process speech media through the shared speechmix voice chain, store each result as an undoable alternate media variant, and preserve the source audio.

**Architecture:** Add variant metadata to the media model and media store, then expose a pure clip-media swap operation through Session. Queue voice processing as cooperative jobs; derive rider masks from `analysis.speech_lanes`, pass the shared chain's own defaults, and save completed output as a new 24-bit FLAC variant. Keep the Inspector toggle for the later UI work package.

**Tech Stack:** Python, NumPy, SoundFile, pytest, `speechmix.chain`, existing Session jobs and History.

---

### Task 1: Media variants

**Files:** `src/kuulas/model.py`, `src/kuulas/history.py`, `src/kuulas/media.py`, `tests/test_voice_chain.py`.

1. Write failing tests that `MediaStore.add_array(audio, name, variant_of)` stores a 24-bit FLAC with the same frame count and persisted `variant_of` / `variant` metadata.
2. Run `pytest tests/test_voice_chain.py -q`; confirm the new API is missing.
3. Add model fields and persist them in the media row's existing `extra` JSON so existing projects need no schema migration. Add `MediaStore.add_array` with a partial file, atomic rename, content hash, peaks, and metadata insertion using the existing media-store finish path.
4. Re-run the focused test and confirm the stored file decodes to the expected shape and the metadata survives reopening History.

### Task 2: Undoable variant selection

**Files:** `src/kuulas/ops.py`, `src/kuulas/session.py`, `tests/test_voice_chain.py`.

1. Add failing tests for switching selected clips from a source to its variant and back, rejecting unrelated media, and undo restoring the source.
2. Add the pure `ops.use_variant(project, clip_ids, media_id)` operation and register the Session command. Validate that the chosen media is the source's variant or the source itself.
3. Confirm the operation changes only named clips and is one History step.

### Task 3: Background voice processing

**Files:** `src/kuulas/session.py`, `tests/test_voice_chain.py`.

1. Add failing Session tests with a deterministic fake `speechmix.chain.process`: selected speech clips produce one variant per source media, clips swap to it, frame counts stay fixed, and Undo restores the originals.
2. Add fault-injection coverage for an unreadable source and a chain failure; failed media must produce no variant and must not stop other media.
3. Queue one cancellable background job per distinct used media. Construct settings from `speechmix.chain` constants, request speech processing with `gain_db=0.0` and `target_lufs=None`, and pass the source track's speaking mask.
4. Store successful output through `MediaStore.add_array`, then make the clip switch in History. Honor playback gating, cancellation, optional plugin path/state, and fail-soft per-media errors.
5. Run the new file alone and the existing jobs, analysis, media, and edit-operation tests.

### Task 4: Format and verification

**Files:** `docs/FORMAT.md`.

1. Document variant metadata in the media-row `extra` object, including the source-media ID and the user-visible variant name.
2. Run `uv run pytest -q` and `uv run ruff check .`.
3. Commit the WP10 backend slice. The Inspector toggle remains for the UI package gated on WP4.
