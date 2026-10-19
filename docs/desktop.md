# Desktop wrapper (WP15)

`src/kuulas/desktop.py`. `kuulas` (no arguments) opens a pywebview window with
the recent projects; `kuulas open <folder> --window` opens a project directly.
The window runs the normal FastAPI app on a free 127.0.0.1 port in a background
thread (`RunningProject`) and stops it when the window closes. Recent projects:
`recent.json` in the per-user config folder (`~/Library/Application Support/kuulas`,
`%APPDATA%\kuulas`, `~/.config/kuulas`), 20 entries, missing folders dropped on read.

The page finds the bridge with `nativeBridge()` (`ui/importing.js`). With it, the
Import button uses a native dialog and a dropped file arrives as a path (pywebview
gives paths only on the Python side), and the project links the file in place
(`POST /api/import`, `copy: false`). In a plain browser nothing changes: the
file input and upload still work. The native menu (File, Edit, View, Window)
calls `window.kuulasNative.menu(id)`. The editor's own File > New project… / Open project…
use the bridge (`new_project_in_window`, `open_project_in_window`): a native dialog, then
the project opens in a window of its own; a plain browser asks for a path instead
(`POST /api/project/new`, `/api/project/open`).

## pywebview limits we design around

- Linux needs system web-view packages: GTK with WebKit2 (`python3-gi`,
  `gir1.2-webkit2-4.1`) or Qt. CI uses GTK/WebKit2 4.1.
- Windows needs the WebView2 runtime.
- macOS WKWebView is Safari's engine: pinch arrives as gesture events.
- Native menus are basic (no icons, shortcuts shown in the menu are not wired).
- No built-in updater. Signing and notarising the Mac app, and packaging
  (PyInstaller), are separate later chores.
- Dropped-file paths exist only through pywebview's own DOM event API.

## Verified and not

Verified (automated, `tests/test_desktop.py`, `ui/tests/native.test.js`): config
folder per OS, recents rules, title, menu model and its translations, the server
thread starting, answering and stopping, no-argument and `--window` routing, the
missing-extra message, bridge detection.

Verified by hand on macOS 15.8.1 (arm64, pywebview 6.2.1), once: `kuulas open
<project> --window` created a 1400x900 on-screen window and the server answered
`/api/state` with 200. Not seen: a screenshot (no screen-recording permission
for the agent), so that the page rendered, and that the window title is right,
were not observed.

Not verified: closing the window by hand (stop on `closed`), the launcher page
and its buttons, the native open/import dialogs, drag-and-drop paths, the menu
items (zoom, density, export call existing buttons), Windows, Linux, and CI
itself (never run; needs the `PODCAST_READ_TOKEN` secret because kuulas imports
the private podcast repo).

## Tester build spike (WP73 part a, 2026-10-19)

Question: can a Briefcase bundle run pywebview with the FastAPI thread, and does a
double-clicked `.kuulas` folder reach the app as an open-files event?

Result: yes, with Briefcase 0.4.6 (no fall-back to PyInstaller needed). A throw-away
app (pywebview 6, fastapi, uvicorn; 126 MB `.app`, 217 MB build folder) was built with
`briefcase create` + `build`, launched with `open -n -a App.app Demo.kuulas`:

- the window opened and the uvicorn thread answered `/api/state` from inside the bundle;
- the open-files event arrived at launch (about 0.4 s after the server started) and a
  second one while running (`open -a App.app Second.kuulas`), as paths, with a package
  type that conforms to nothing registered (`open -a` sends the event whatever the type);
- how: pywebview's `BrowserView.AppDelegate` has no `application:openFiles:`; adding the
  method to that class with `objc.classAddMethod` before `webview.start()` is enough, and
  the delegate then replies `replyToOpenOrPrint_(0)`.

Things the spike found that shape the build:

- Briefcase installs wheels only (`--only-binary`). `proxy_tools`, which pywebview needs,
  has no wheel, so `scripts/build_wheels.sh` builds one and passes it through
  `requirement_installer_args = ["--find-links=..."]`.
- Briefcase refuses a project without a PEP 639 licence definition.
- The Info.plist template supports `CFBundleTypeRole`, `LSHandlerRank`,
  `LSItemContentTypes` and `UTTypeConformsTo` per document type, so no plist patching:
  `LSHandlerRank = "Owner"` is what makes it write the *exported* UTI declaration, and
  `UTTypeConformsTo = ["com.apple.package", ...]` makes the folder a package.
- `BRIEFCASE_HOME` moves Briefcase's template and support-package cache out of `~/Library/Caches`.

## Tester build: dependencies, ffmpeg, UI files (WP73 part b)

- **speechmix and nhsx** are path dependencies on `../podcast/packages/`. The bundle
  installs their wheels instead: `scripts/build_wheels.sh <folder>` clones the podcast
  repo's `origin/main` (read only; the working checkout, dirty or not, is never touched)
  and runs `uv build --wheel` on both. `PODCAST_SRC=<clean checkout>` uses one you made.
- **ffmpeg: bundled.** Checked with `soundfile.available_formats()` (libsndfile 1.2.2):
  it reads WAV, FLAC, OGG, MP3 and AIFF in-process. It does not read m4a, aac, mp4, mov,
  mkv or webm, which the import dialog offers (phone recordings are m4a), and kuulas
  needs `ffprobe` to measure them. Export to MP3, AAC, Opus and Vorbis also runs
  `ffmpeg`. A double-clicked app has a minimal `PATH` (no Homebrew), so a tester's Mac
  would fail on exactly the common files. `scripts/fetch_ffmpeg.sh <folder>` fetches
  static arm64 `ffmpeg` and `ffprobe` (132 MB together, compress to about 50 MB in the
  dmg); the app puts its own `Resources/bin` first on `PATH` (speechmix's
  `get_binary_path` only looks at `PATH` outside PyInstaller).
- **Licence of the bundled ffmpeg.** The builds are from <https://ffmpeg.martin-riedl.de>
  (release builds, `--enable-gpl --enable-version3`, so GPLv3; they include libmp3lame,
  libopus, libvorbis and the AudioToolbox AAC encoder). They are separate programs
  that kuulas starts as subprocesses, not linked into it, so kuulas's own licence is not
  affected; the GPL requires that the recipient can get the source, which that site and
  <https://ffmpeg.org> provide. The dmg's notice (`docs/TESTERS.md`) names this. If kuulas
  is ever distributed beyond testers, re-check with the ffmpeg build used then.
- **UI files.** `kuulas.paths.find_ui_dir` looks in `kuulas/ui` (wheel), `ui` beside the
  package (the bundle: Briefcase copies each source folder into `Resources/app`) and the
  repo's `ui` (checkout), and takes the first that has an `index.html`.
- **The recorder (WP12a).** `src/kuulas_recorder` is a third Briefcase source folder. It runs
  as its own processes, started as `<the app's executable> -m kuulas_recorder ...`;
  `kuulas.bundle.main` passes those arguments to the recorder before it opens the log.
  `--selftest` records one second from the recorder's fake source. Not yet tried in a built
  app (whether Briefcase's launcher passes `-m` through as arguments is untested; both
  cases are handled).

## Tester build: the app, the file type, the dmg (WP73 parts c to e)

Build (Apple-silicon Mac, uv, network; HEAD of the checkout, nothing else):

```
scripts/build_dmg.sh            # writes dist/Kuulas <version>.dmg and prints size + sha256
```

It exports HEAD with `git archive`, builds the wheels (`build_wheels.sh`), fetches ffmpeg
(`fetch_ffmpeg.sh`), stages a Briefcase project (`stage_bundle.py`), runs
`briefcase create`, copies ffmpeg into `Contents/Resources/bin` before `build` (which
signs ad hoc), runs `Kuulas.app --selftest`, packages the dmg, mounts it and runs
`--selftest` on the app inside. Everything lives in `build/dmg` (git-ignored); the
Briefcase cache is there too (`BRIEFCASE_HOME`), so `rm -rf build` frees all of it.
Measured 2026-10-19 on an M1 Max: the app is 556 MB (scipy 96, llvmlite 125, ffmpeg and
ffprobe 126, Python 93, numpy 39, numba 14), the dmg 165 MB.

- **Entry point.** `python -m kuulas` (`bundle.py`): the log goes to
  `~/Library/Logs/Kuulas/kuulas.log` (1 MB, 3 kept; also stdout, stderr and
  `faulthandler`), the bundled `bin` is first on `PATH`, `NUMBA_CACHE_DIR` is
  `~/Library/Caches/Kuulas/numba` (numba would otherwise write into the signed bundle),
  Finder's `-psn_` argument is dropped. No arguments opens the launcher (`kuulas desktop`);
  the other `kuulas` commands work with the bundle's executable too, and
  `--selftest`/`--help` print to the terminal instead of the log. The build label is
  baked in (`kuulas/build_label.txt`, read by `build_info.baked_label`) because a bundle has
  no git checkout.
- **File type.** `stage_bundle.render_config` is the one place that defines it:
  bundle id `fi.sulopuisto.kuulas`, document type `kuulas` (role Editor, rank Owner), an
  exported type `fi.sulopuisto.kuulas.project` conforming to `com.apple.package` and
  `public.composite-content`. Checked in the built `Info.plist` (`plutil -p`).
  WP72's `macapp` module was not on main when this was written, so these identifiers exist
  twice once it lands; keep them equal.
- **Open events.** `desktop.install_open_files_hook` adds `application:openFiles:` to
  pywebview's app delegate (see the spike above). `WindowApp` receives the paths
  (`openfiles.project_paths` keeps `.kuulas` folders and folders with a manifest): at
  launch the project replaces the launcher in the first window; later ones open a new window;
  a project already open is brought forward (two servers on one project would fight over its
  lock). The menu bar acts on the window that is in front.
- **Not in the bundle:** `ui/tests`, `biome.json`, the docs. Unsigned and not notarised; the
  testers' steps are `docs/TESTERS.md`.

Verified headlessly: the unit tests (`tests/test_open_files.py`, `test_bundle.py`,
`test_stage_bundle.py`, `test_ui_dir.py`); the whole build from a clean `git archive`;
`--selftest` on the built app and on the app inside the mounted dmg; the built `Info.plist`;
and, with a copy of the built app in a temp folder (registered with Launch Services there
only, unregistered after): `open -n -a Kuulas.app One.kuulas` opened that project (the
log shows the server and project opening), a second `open -a ... Two.kuulas` opened a
second project in the same process, and a repeat of `One.kuulas` opened nothing new.

Not verified (needs a person at the screen): that the windows look right (no screenshot
was possible), opening the dmg and dragging to Applications, the right-click Open step,
that Finder shows a `.kuulas` folder as one file with the icon and that a Finder
double-click opens it (the `open -a` test sends the same Apple event but skips the Finder
type lookup), "Open with", the Dock-icon drop, the microphone prompt, a Mac that is not
this one (a clean user, no Homebrew), macOS older than 15.

## Kuulas.app: double-click a `.kuulas` folder on macOS (WP72 step 1)

A project is a folder. A small launcher app, `Kuulas.app`, makes Finder show a
`Name.kuulas` folder as one file with the kuulas icon, and open it by double-click,
"Open with...", or by dropping it on the app or its Dock icon. It is an AppleScript
droplet built locally with `osacompile`: no PyInstaller, no signing, nothing in
`/Applications`. Code: `src/kuulas/macapp.py` (pure parts, tested in
`tests/test_macapp.py`), `scripts/make_app.py` (entry point).

What it does: for each project it runs the README command in the background,
`uvx --from "<repo>[desktop]" --with-editable "<repo>[desktop]" kuulas open <project>
--window` (one window, one process per project; output in `~/Library/Logs/Kuulas.log`).
Opened with no document it runs `kuulas desktop` (the launcher with recent projects).
The repository path is written into the app when it is built; if the repo moves, the
app says so and asks you to build it again. The `uvx` and `uv` paths are fixed at build
time too (the app starts with almost no `PATH`), so rebuild after moving uv.

Build and register (never needs sudo):

```bash
uv run python scripts/make_app.py --dry-run     # print the plan, change nothing
uv run python scripts/make_app.py               # ~/Applications/Kuulas.app, then register
uv run python scripts/make_app.py --into DIR --no-register   # elsewhere, no Finder registration
```

Rebuilding replaces the app. Registration is `lsregister -f` (Launch Services learns the
type `fi.sulopuisto.kuulas.project`, a package type conforming to `com.apple.package`
and `public.composite-content`, extension `kuulas`; bundle id `fi.sulopuisto.kuulas`).
Undo:

```bash
LSR=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
$LSR -u ~/Applications/Kuulas.app && rm -rf ~/Applications/Kuulas.app
```

If Finder still shows a folder after building, `killall Finder` (or log out) makes it
re-read the types.

**Already open.** Before starting a project, the app asks `macapp.py check` (run with
`uv run --no-project`): it reads the project's `locks/*.json` and, when a lock names
this computer, has a fresh heartbeat (under 2 minutes) and a live pid, it does not
start a second kuulas; it brings that process forward through System Events
(`set frontmost`). macOS asks once whether Kuulas may control System Events; if you
refuse, nothing is brought forward and no second window opens either, the click just
does nothing. A project open on another computer (Dropbox) is not checked: kuulas
itself then warns about the other computer's lock when the window opens.

**Dropbox.** A `.kuulas` folder in Dropbox works the same. Dropbox shows it as a
folder; Finder's file look comes from the type registered on this Mac, so each Mac
needs its own build and registration.

**Limits.** Local build only, not signed or notarised: it cannot be handed to other
people (step 2: py2app/PyInstaller, signing). Launching takes as long as `uvx` takes
(a few seconds; there is no progress, a failure is only in the log). The Dock icon menu
does not list recent projects. Windows and Linux cannot give a folder a file
association; not covered.

Verified by tests: the plist content, quoting of paths with spaces and quotes, which
folders count as projects, the lock rules, the dry-run plan, and on macOS a build into
a temp folder (`plutil -lint`, bundle present, icons). Only by hand: Finder showing the
folder as a file, double-click, "Open with...", dropping on the app and the Dock icon,
the brought-forward window, the System Events permission prompt.

Both apps: the WP72 launcher (`scripts/make_app.py`, in `~/Applications`) and this bundle
declare the same bundle id and type, so a Mac that has both has two apps claiming
`.kuulas`; Finder uses one of them. A test (`tests/test_stage_bundle.py`) keeps the
identifiers equal to `macapp`. Testers have only the bundle; on the owner Mac, unregister
the launcher (`make_app.py` prints how) before trying the dmg.
