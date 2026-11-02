# Consolidated FLAC and WAV Relinking

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep consolidated PCM media as lossless FLAC and let matching FLAC files replace supported WAV sources without changing clip identity.

**Architecture:** Preserve raw file SHA-256 as the canonical media id. Store a second, narrowly scoped fingerprint over decoded integer PCM samples for supported WAV sources, and accept a FLAC candidate only when sample rate, channel count, frame count, bit depth and fingerprint match. Use the same comparison for explicit replacement and missing-media relinking.

**Tech Stack:** Python 3.13, SoundFile/libsndfile, NumPy, SQLite media metadata.

---

### Task 1: Persist WAV sample identity

**Files:**
- Modify: `src/kuulas/media.py`

Capture a deterministic fingerprint while reading eligible WAV PCM during linked import or WAV-to-FLAC encoding. Keep it in the existing `media.extra` JSON, so no SQLite migration is needed. Do not fingerprint lossy, float, resampled, or unsupported PCM sources.

### Task 2: Accept equivalent FLAC relinks

**Files:**
- Modify: `src/kuulas/media.py`
- Modify: `src/kuulas/session.py`

Allow only a `.wav` source identity to match a `.flac` candidate with identical decoded PCM metadata and fingerprint. Preserve the original media id and displayed source name. Apply the rule to explicit replacement, manual relinking, and automatic recovery; retain strict file SHA-256 identity for all other cases.

### Task 3: Document the compatibility rule

**Files:**
- Modify: `docs/FORMAT.md`
- Modify: `ROADMAP.md`
- Modify: `CHANGELOG.md`

Explain raw-file identity and the exact WAV-to-FLAC exception. Keep the project schema unchanged.
