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

The first time you record, macOS asks for microphone access. Say yes: without it the input
is silent rather than an error (the record view's meter stays at the bottom). To change
your answer later: System Settings > Privacy & Security > Microphone. When Kuulas runs from
a terminal (a development run, `uv run kuulas`), it is the terminal app that needs the
permission.

Recording (Transport > Record…): the takes are WAV files in the project's `recordings`
folder. Nothing plays while a take records; listen through your audio interface. Stopping
takes two presses of Stop (or Space) by default; Transport > "Stopping a recording" chooses
one click or a 2-second hold instead. Closing the window does not stop a take: open the
project again and the record view comes back. Please report anything that lost audio.

## Which build is this

The build label (for example `v26.10.19.6+4d4611f`) is in the status bar of the editor
window. The same label is the first line of the log each time the app starts.

## Reporting a problem

Send:

1. the build label,
2. what you did and what you expected,
3. the log file: `~/Library/Logs/Kuulas/kuulas.log` (Finder: Go > Go to Folder, paste the
   path). It rotates at 1 MB and keeps `kuulas.log.1` to `.3`; send the newest two,
4. for a crash, the report in Console.app under Crash Reports (look for "Kuulas"),
5. if it is slow: see below.

### If it is slow

Do this **while it is slow** (for example while a long project plays): Help > **Record a
performance report…**, choose 30 seconds (10 or 60 also work), Start, and keep doing the
slow thing. When it finishes, Finder shows `~/Library/Logs/Kuulas/performance-<time>.txt`.
Send that `.txt`. It lists the program's threads, the busiest functions, process CPU,
memory and the length of a playback block; it has no project names, file names or
recording text. It needs no password or developer tools.

For a more detailed log: Help > **Log level** > Detailed (debug), repeat the problem,
then send `kuulas.log`. Set it back to Normal afterwards (the log grows fast). From a
terminal, `KUULAS_LOG_LEVEL=DEBUG` and `KUULAS_PROFILE=30` (seconds, from start-up) do
the same.

Your recordings and edits are in the project folder, not in the app; removing the app
does not touch them.

## Check that an install works

```
/Applications/Kuulas.app/Contents/MacOS/Kuulas --selftest
```

Prints one line per check (libraries, ffmpeg, interface files, a project and the server,
the loudness meter, the recorder recording one second from a built-in test signal) and
ends with `selftest passed`. No window opens and no microphone is used.

## What is inside

Python and the libraries Kuulas uses, with their own licences (in
`Kuulas.app/Contents/Resources/app_packages/`). `ffmpeg` and `ffprobe` are in
`Kuulas.app/Contents/Resources/bin`: static builds from <https://ffmpeg.martin-riedl.de>,
licensed GPL version 3; they run as separate programs, and their source is available from
<https://ffmpeg.org>.

## Remove

Drag Kuulas to the Bin. Optional leftovers: `~/Library/Logs/Kuulas`,
`~/Library/Caches/Kuulas`, `~/Library/Application Support/kuulas` (the recent-projects list).
