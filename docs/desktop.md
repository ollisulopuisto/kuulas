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
calls `window.kuulasNative.menu(id)`.

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
