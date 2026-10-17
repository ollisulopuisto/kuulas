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

Verified by hand on macOS 26.10 (arm64, pywebview 6.2.1), once: `kuulas open
<project> --window` created a 1400x900 on-screen window and the server answered
`/api/state` with 200. Not seen: a screenshot (no screen-recording permission
for the agent), so that the page rendered, and that the window title is right,
were not observed.

Not verified: closing the window by hand (stop on `closed`), the launcher page
and its buttons, the native open/import dialogs, drag-and-drop paths, the menu
items (zoom, density, export call existing buttons), Windows, Linux, and CI
itself (never run; needs the `PODCAST_READ_TOKEN` secret because kuulas imports
the private podcast repo).
