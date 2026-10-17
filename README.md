# kuulas

kuulas is a multitrack editor for spoken word (podcasts, interviews, radio).
It is modelled on Hindenburg PRO: keyboard-first, with the transcript and the
audio as one thing. Its signal processing comes from the podcast repo's
`speechmix` and `nhsx` packages.

## Running the tests

kuulas needs the podcast repo checked out next to it, at `../podcast`, because
`speechmix` and `nhsx` are path dependencies.

```
uv sync
uv run pytest -q
uv run ruff check .
node --test ui/tests/                       # UI unit tests
npx @biomejs/biome@2.2.4 check ui/         # UI lint
```

Audio decoding uses ffmpeg. Install it first (`brew install ffmpeg` on a Mac).

Tests that need a real audio device are kept out of the default run. Run them
by hand, volume down (plays one second of a quiet tone):

```
uv run pytest -q tests/hardware -s
```

The transcription smoke test needs faster-whisper, installed with the
`transcribe` extra:

```
uv sync --extra transcribe
uv run pytest -q tests/manual/test_transcribe_smoke.py -s
```

Check test isolation: the default language follows the machine, so a test can
pass or fail depending on run order (`uv run python scripts/check_isolation.py`).

## Projects

A project is a `Name.kuulas` folder (format: `docs/FORMAT.md`). To see what
is in one:

```
uv run kuulas info Interview.kuulas
```

To open one (it is created if missing) in the browser, served on 127.0.0.1
only: `uv run kuulas open Interview.kuulas`. The page is a placeholder until
the UI (WP4) lands; the HTTP API behind it is described in `docs/PLAN.md`
(WP3). What is done and what is left: `ROADMAP.md`.

The `kuulas.usage.extract(project)` API lists the recording-time ranges used
by a project, including audibility and excerpt-to-original mapping. Its
results are shared by future music reports, series tracking and change views.

## Desktop app

A native window instead of a browser tab (WP15): it frees the keys a browser
keeps (Cmd+T, Cmd+W, Cmd+N, F6, Cmd+L) and adds native file dialogs, a menu and
drag and drop that links media in place instead of uploading it. It uses the
system web view through pywebview and the same server as `kuulas open`.

```
uv sync --extra desktop            # installs pywebview
uv run kuulas                      # window with a recent-projects list
uv run kuulas open Interview.kuulas --window
```

Without the extra, `kuulas` says how to install it; `kuulas open <folder>`
without `--window` keeps serving to a browser.

Per OS: macOS uses WKWebView (Safari's engine). Windows needs the WebView2
runtime (already on Windows 11). Linux needs system packages first:
`python3-gi gir1.2-webkit2-4.1` (Debian/Ubuntu) and a PyGObject install. Not
signed or notarised; no updater. Details and what is verified: `docs/desktop.md`.

## Where to read next

- `ROADMAP.md`: what kuulas must do, what is done, and what is next.
- `docs/PLAN.md`: how it is built, in work packages, with the ground rules.
