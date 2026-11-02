# Colab Faster-Whisper Integration Plan

**Goal:** Make the packaged Kuulas app run its Whisper option from the podcast revision that uses faster-whisper and supports T4 GPUs.

**Architecture:** Keep Colab transcription in the shared podcast `colab-transcribe` tool; Kuulas only pins the public revision in its runtime command. Update the pin to podcast `main` commit `8fc54ff6dfde7d2cce71eff6b1dc93196eba56de`, which preserves Parakeet Ultra while selecting `faster-whisper==1.2.1` for Whisper. Guard that pin with a Kuulas test, then prepare and publish a new DMG release.

**Tech Stack:** Python, pytest, `uv`, GitHub Actions macOS DMG workflow.

---

### Task 1: Pin Kuulas to the podcast Faster-Whisper implementation

**Files:**
- Modify: `src/kuulas/colab_transcribe.py`
- Test: `tests/test_colab_transcribe.py`
- Modify: `docs/PLAN.md`, `CHANGELOG.md`, `ROADMAP.md`, `pyproject.toml`, `uv.lock`

**Steps:**
1. Update the public-command regression to expect podcast commit `8fc54ff6dfde7d2cce71eff6b1dc93196eba56de`.
2. Run the focused test and confirm it fails against the old pin.
3. Change the runtime command pin; keep the user-facing Whisper model ID and Parakeet Ultra choice unchanged.
4. Run the focused test, then the full Python, Ruff and UI verification required by the repo. Retry Biome if npm access is available.
5. Bump Kuulas to `26.11.1.3`, document the faster-whisper/T4 fix, commit and tag.
6. Push the release tag to start the GitHub-hosted DMG build; download and verify the release asset.

**Acceptance:** The packaged command fetches a public podcast revision whose Whisper path installs `faster-whisper==1.2.1` and uses `large-v3-turbo` with CUDA `float16`; Parakeet Ultra remains available. The DMG is checksum-verified.
