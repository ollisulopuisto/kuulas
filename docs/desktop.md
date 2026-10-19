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
