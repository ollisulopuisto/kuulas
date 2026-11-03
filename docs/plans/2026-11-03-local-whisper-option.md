# Local Whisper and Orukeet Options

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make local Whisper the default transcription engine, offer Orukeet as the faster alternative, and keep Colab on Podcast's remote pipeline.

**Architecture:** Keep local engine selection separate from the Colab backend. Use faster-whisper for full-length local audio and Podcast's `wordalign` package in its own process to refine Whisper word starts. Preserve Orukeet's native local timings and live recording path.

**Tech Stack:** Python 3.13, faster-whisper, Podcast `wordalign`, FastAPI, vanilla JS and localized EN/FI strings.

---

### Task 1: Local engine contract

Add a `local_engine` job/API field defaulting to `whisper`, validate `whisper|orukeet`, preserve it when jobs restart, and dispatch to the selected local implementation. Keep Colab independent of the local engine field. Add regression tests before implementation.

### Task 2: Local Whisper worker and word timing

Restore Kuulas's faster-whisper path with `large-v3-turbo` as the default. Keep model loading warm for all media in a job, use full-file transcription with VAD and native word timestamps, refine starts through Podcast's `wordalign` process, and fall back to Whisper timings with a visible warning if alignment is unavailable. Cover engine output and worker cancellation/failure with fakes.

### Task 3: Local engine choices in UI

Make the ordinary local transcription action use Whisper. Add a discoverable Orukeet action labeled faster, and label Whisper as higher accuracy. Show the choices where transcript rows offer transcription. Run UI tests, Node tests, Biome, pytest, and Ruff.

### Task 4: Dependencies and operator notes

Add the shared `wordalign` dependency and local Whisper runtime dependency, update the user help in English and Finnish, and document the first-run model/alignment download behavior. Do not change the Colab execution path.
