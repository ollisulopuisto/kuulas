# Live Transcription Toggle Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make live transcription an explicit opt-in that can be enabled before a take or toggled while it records.

**Architecture:** Keep the preference in the record UI's existing user preference store, with an absent preference meaning off. Pass the selected value when starting a take, expose runtime enable/disable on the recording API, and pause/resume the current live-transcription runner without affecting audio capture. Show a translated toggle in setup and in the live recording transcript panel, with availability and off states explained.

**Tech Stack:** Python/FastAPI, record session and live transcription runner, browser UI JavaScript, English and Finnish locale JSON, pytest, Node tests, Biome.

---

### Task 1: Opt-in recording session behavior

**Files:**
- Modify: `src/kuulas/record_session.py`
- Modify: `src/kuulas/server.py`
- Test: `tests/test_record_session.py`
- Test: `tests/test_server.py`
- Test: `tests/test_live_transcribe.py`

1. Add failing tests for live transcription being off by default, unavailable engines, starting a take with it enabled, and enabling/disabling it while recording.
2. Run those tests and confirm they fail because the session currently starts the live runner automatically and has no runtime toggle.
3. Add explicit session state and a runtime API; pause/resume the current runner so toggling does not restart or duplicate processed words. Stop with flushing only when live transcription remains enabled.
4. Run the focused Python tests and confirm opted-in words still hand off and disabled takes do not transcribe.

### Task 2: Discoverable UI toggle

**Files:**
- Modify: `ui/record-view.js`
- Modify: `ui/api.js`
- Modify: `ui/record-model.js` if pure state helpers are useful
- Modify: `ui/tests/record-model.test.js` and focused recording UI tests
- Modify: `src/kuulas/locales/en.json`
- Modify: `src/kuulas/locales/fi.json`

1. Add failing tests for the preference defaulting to off and for the toggle appearing and sending the requested state before and during recording.
2. Run those tests and confirm they fail for missing toggle behavior.
3. Add the persisted user preference, setup checkbox, and live recording checkbox. Keep both controls synchronized, make unavailable state clear, and show an explicit off message in the transcript panel.
4. Run focused Node tests and Biome; confirm English/Finnish localization checks pass.

### Task 3: Review and commit

1. Run the new test files independently, then the required Python and UI checks from `AGENTS.md`.
2. Inspect the full diff and `git diff --check`.
3. Commit the feature on this branch and report the commit, checks, and any real-device limitations.
