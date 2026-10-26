# kuulas

kuulas is a local multitrack audio editor for spoken word (podcasts, interviews, radio). It is modelled on Hindenburg PRO: keyboard-first, speech-aware, with the transcript and the audio treated as one thing. The engine runs locally on Python 3.13 and serves a browser UI over local HTTP/WebSocket; audio analysis and signal processing come from the podcast repo's `speechmix` and `nhsx` packages.

**Kuulas is a free, open-source podcast editor. It can mix your episode for you, and it keeps every edit you ever made, so you can go back to any moment and never lose a thing.**

Taglines (use either, not together): *"A podcast editor where nothing is ever lost."* or *"Every edit. Every version. One click back."*


## What works today

- **Multitrack editor window**: Timeline with comfortable (80 px) and compact densities, waveform pyramid rendering, overview navigation strip, and live WebSocket playhead feed.
- **Hindenburg-level keyboard editing**: Full customizable keymap (`?` cheat sheet), B split (Shift+B all tracks), Backspace/Delete soft cut, X ripple cut, Q/W trim to cursor, N mute, Shift+M track mute, Shift+S solo, E group editing, and modifier nudge/gain controls.
- **Contextual help and command palette**: Docked F1 help panel with topic search and "Show me" ring highlights, Mod+K palette, and in-window menu bar with live modifier previews.
- **Clipboard with persistent history**: Mod+C / X copy, Mod+V insert paste (sync groups follow), Alt+Mod+V overwrite, and sidebar Clipboard tab with cross-project history, pin, rename, and delete.
- **Auto-Silence and non-destructive gates**: Speech activity analysis marks closed-mic stretches as gates with smooth 30 ms boundaries; visible in the editor and reopenable stretch by stretch.
- **Batch import with flexible placement**: Import multiple files side by side (aligned by BWF recording clocks into sync groups) or sequentially on one track, with natural name sorting and track naming by file or person.
- **Sync groups and edit expansion**: Tracks recorded together stay locked; edits time-shift the entire sync group; subclips can be resynced to the main clip.
- **Music reporting**: Session royalty reports (CSV with formula injection protection, HTML) via CLI and `/api/music-report`.
- **Transcription**: Local faster-whisper and Colab transcription. In a source checkout beside the current podcast repository, Colab uses that checkout's tool; Orukeet filler words and repetitions stay in the transcript and can become cut candidates.
- **Project format (v3)**: Crash-safe `Name.kuulas` package directory, WAL SQLite history tree with constant-time branching undo/redo, and recording clock in flicks.
- **Desktop app wrapper**: Native window via pywebview (`--extra desktop`), recent projects window, native file dialogs, and local file drag-and-drop linking.

*Verification note:* GitHub Actions is configured to run the test and desktop smoke jobs on macOS, Windows and Linux. Windows runs editor coverage and desktop smoke; it omits recorder, analysis-worker, and detached-transcription worker integration, automixer integration for macOS-only process and path behavior, and the macOS DMG build-script test. Those tests remain covered on macOS; the recorder and analysis worker are also covered on Linux. Nobody has yet listened to playback on a real audio device with this version, or looked at the desktop window by eye.

## Running kuulas

kuulas requires Python 3.13 and `uv`. Audio decoding uses ffmpeg (`brew install ffmpeg` on macOS). kuulas needs the podcast repo checked out next to it at `../podcast` because `speechmix` and `nhsx` are path dependencies.

From any folder, without `cd`ing to the repo (tested 2026-10-19 from the home folder):

```bash
K=~/Documents/koodi/kuulas
uvx --from "$K[desktop]" --with-editable "$K[desktop]" kuulas desktop
```

The `--with-editable` part is needed: the UI files (`ui/`) are read from the repository, and a plain
`uvx --from <folder>` installs a copy in uv's cache where `ui/` does not exist (the window then shows only
a placeholder page). `speechmix` and `nhsx` are found through the repo's `../podcast` paths, so the podcast
checkout must still sit next to it. A shell alias makes it one word:
`alias kuulas='uvx --from "$K[desktop]" --with-editable "$K[desktop]" kuulas'`.

To inspect or open a project (created automatically if missing):

```bash
uv run kuulas info Interview.kuulas
uv run kuulas open Interview.kuulas
```

This starts the local backend server on `127.0.0.1` and opens the editor in your default browser.

### Desktop app

To run kuulas in a native window (which frees browser-reserved shortcuts like Cmd+W and Cmd+T, adds native file dialogs, and links dropped files in place):

```bash
uv sync --extra desktop
uv run kuulas                         # opens launcher with recent projects
uv run kuulas open Interview.kuulas --window
```

Platform requirements: macOS uses WKWebView (Safari engine); Windows requires WebView2 runtime; Linux requires GTK WebKit2 packages (`python3-gi`, `gir1.2-webkit2-4.1`). See `docs/desktop.md`.

**Mac test build (no Python needed):** `scripts/build_dmg.sh` makes an unsigned `Kuulas <version>.dmg`; testers follow `docs/TESTERS.md`.

## Testing and checks

Run the complete automated test and lint suite:

```bash
uv sync
uv run pytest -q                      # Python unit tests (1000+ tests)
uv run ruff check .                   # Python lint
node --test ui/tests/                 # UI unit tests (500+ tests)
npx @biomejs/biome@2.2.4 check ui/    # UI lint and format
```

Repository verification tools in `scripts/`:

```bash
uv run python scripts/check_isolation.py  # Run every test file alone to ensure test isolation
uv run python scripts/check_locale.py     # Verify English/Finnish translation parity and references
uv run python scripts/check_docs.py       # Check CalVer, pyproject.toml, and roadmap alignment
```

Optional and manual tests:

```bash
# Real audio output test (volume down; plays a short quiet tone)
uv run pytest -q tests/hardware -s

# Local transcription smoke test (requires faster-whisper)
uv sync --extra transcribe
uv run pytest -q tests/manual/test_transcribe_smoke.py -s
```

## Documentation and development

- `ROADMAP.md`: What kuulas must do, requirements status, and planned milestones.
- `docs/PLAN.md`: Implementation work packages, triage, and project ground rules.
- `docs/FORMAT.md`: On-disk package structure, SQLite history, and material catalog.
- `docs/desktop.md`: Desktop wrapper architecture, pywebview boundaries, and verification.

agents work through `.agents/` and `scripts/agent_gate.py`.

## License

Kuulas is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License, version 3 or (at your option) any later version. See [LICENSE](LICENSE). Licences of what the .dmg bundles (pedalboard, ffmpeg and others): [docs/LICENSES.md](docs/LICENSES.md).

Copyright (c) 2026 Olli Sulopuisto.
