# Colab Model Selection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let users choose the transcription engine used by Kuulas's Colab backend, with Whisper large-v3-turbo as the preferred quality option and Parakeet Ultra as the alternative.

**Architecture:** Replace the ambiguous free-text model field in Colab settings with translated built-in choices plus a custom-ID entry. Persist and pass the selected identifier unchanged; migrate the old `turbo` default to `whisper` because the shared CLI uses `whisper` for Whisper large-v3-turbo. Local Orukeet remains unchanged.

**Tech Stack:** Browser UI modules, shared locale catalogs, pure JavaScript settings model and Node tests; Kuulas delegates inference to the adjacent podcast `colab-transcribe` CLI.

---

## Scope and dependency

The Colab settings UI will offer:

- `whisper`: Whisper large-v3-turbo on Colab (Photon runtime).
- `parakeet-ultra`: Parakeet Ultra on Colab (Photon runtime).

Podcast main revision `5a179e6f16024a0e1aa6fa9d01a0edcb09cdf2fc` supports both CLI model IDs. Kuulas's packaged command must pin that revision; the DMG workflow's separate Podcast pin does not control the Colab CLI. Do not use the dirty sibling checkout as evidence for packaged compatibility.

## Task 1: Model choice behavior

**Files:**

- Modify `ui/colab-model.js`.
- Test `ui/tests/colab.test.js`.

1. Add constants for the two built-in Colab model IDs and a custom model choice.
2. Treat legacy `turbo` as `whisper`; retain a valid selected ID; use `whisper` when there is no saved model.
3. Verify settings save the selected ID as `model`.
4. Run `node --test ui/tests/colab.test.js`.

## Task 2: Translated selection UI

**Files:**

- Modify `ui/colab-dialog.js`.
- Modify `src/kuulas/locales/en.json` and `src/kuulas/locales/fi.json`.
- Test `ui/tests/colab.test.js`.

1. Replace the model text input with a labeled native select, using model IDs as option values and translated descriptive labels.
2. Verify opening the settings maps legacy `turbo` to Whisper large-v3-turbo and saving writes `whisper`; selecting Parakeet writes `parakeet-ultra`.
3. Verify keyboard use and translated labels in both locale catalogs.
4. Run the focused Node tests and UI lint checks.

## Task 3: Documentation and compatibility note

**Files:**

- Modify `ui/help/en/colab.md` and `ui/help/fi/colab.md`.
- Update help to describe model selection, custom command IDs, and the local-versus-packaged command source.

Explain that model selection applies to Colab; local transcription continues to use Orukeet. Run `python scripts/check_docs.py`, `uv run ruff check .`, `node --test ui/tests/`, and `npx --yes @biomejs/biome@2.2.4 check ui/` before commit. Verify the pinned CLI accepts both model IDs and Kuulas accepts its timing labels.
