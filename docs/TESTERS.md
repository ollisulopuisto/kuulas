# Kuulas test build for Mac

You need an Apple-silicon Mac (M1 or newer) with macOS 12 or later. Nothing else:
no Python, no ffmpeg, no installer.

## Install

1. Open `Kuulas <version>.dmg`.
2. Drag **Kuulas** onto the **Applications** folder in the same window.
3. Eject the disk image.

## First open (the app is not signed)

The build is not notarised by Apple, so macOS blocks it the first time. Once:

1. In Applications, **right-click Kuulas, choose Open**, then **Open** in the dialog.
   (A double-click shows only "cannot be opened" with no Open button.)
2. If macOS 15 or later still refuses: System Settings, Privacy & Security, scroll to
   "Kuulas was blocked", **Open Anyway**.
3. Or in Terminal, remove the download mark and open it normally:

   ```
   xattr -dr com.apple.quarantine /Applications/Kuulas.app
   ```

After that it opens with a double-click like any app. A new build you download is
blocked again the same way.

## Projects

A Kuulas project is a folder called `Name.kuulas`. Finder shows it as one file with the
Kuulas icon (after the app has been opened once from Applications), and **double-clicking
it opens it in Kuulas**. Open several and each gets its own window. A project already
open is brought to the front, not opened twice. File > New project… and Open project… in the editor each open a project in a window of its own.

The first time you record, macOS asks for microphone access.

## Which build is this

The build label (for example `v26.10.19.6+4d4611f`) is in the status bar of the editor
window. The same label is the first line of the log each time the app starts.

## Reporting a problem

Send:

1. the build label,
2. what you did and what you expected,
3. the log file: `~/Library/Logs/Kuulas/kuulas.log` (Finder: Go > Go to Folder, paste the
   path). It rotates at 1 MB and keeps `kuulas.log.1` to `.3`; send the newest two,
4. for a crash, the report in Console.app under Crash Reports (look for "Kuulas").

Your recordings and edits are in the project folder, not in the app; removing the app
does not touch them.

## Check that an install works

```
/Applications/Kuulas.app/Contents/MacOS/Kuulas --selftest
```

Prints one line per check (libraries, ffmpeg, interface files, a project and the server,
the loudness meter) and ends with `selftest passed`. No window opens.

## What is inside

Python and the libraries Kuulas uses, with their own licences (in
`Kuulas.app/Contents/Resources/app_packages/`). `ffmpeg` and `ffprobe` are in
`Kuulas.app/Contents/Resources/bin`: static builds from <https://ffmpeg.martin-riedl.de>,
licensed GPL version 3; they run as separate programs, and their source is available from
<https://ffmpeg.org>.

## Remove

Drag Kuulas to the Bin. Optional leftovers: `~/Library/Logs/Kuulas`,
`~/Library/Caches/Kuulas`, `~/Library/Application Support/kuulas` (the recent-projects list).
