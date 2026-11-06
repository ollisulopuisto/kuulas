# Transcript provenance and safe reruns

## Goal
Show when and how each current transcript was created, and let the user rerun it only after an explicit confirmation. A successful rerun becomes a new transcript revision; failed jobs leave the current transcript untouched.

## Changes
- Persist provenance (backend, engine, model, language) with the existing transcript revision timestamp.
- Return current revision metadata with `/api/words` and display it in the transcript dock.
- Add per-recording rerun actions that repeat the prior backend/engine/model/language when known, falling back to local Whisper for imported/legacy transcripts.
- Confirm replacement, explicitly explaining that the existing transcript remains available in history. Keep confirmation text in English and Finnish.
- Add backend/API and UI model regression coverage; retain prior transcript revision and current pointer on failed transcription.

## Verification
Run focused Python and Node tests first, then required full pytest, Ruff, Node UI tests, and Biome checks.
