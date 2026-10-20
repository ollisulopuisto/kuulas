# M1 verification: what the owner needs to try

M1 is "First playable build": run kuulas, import, listen, edit by keyboard and mouse, undo, export WAV or MP3.
Its items count as built and merged (ROADMAP "Milestones"); this list is what the owner still has to confirm in
the installed app. Report a failure to the coordinator (it goes into `docs/BUGS.md`; only the owner closes items).
Use the latest dmg from GitHub Releases (`xattr -dr com.apple.quarantine` on the dmg and the app first).

Use a copy of a real episode (two or three tracks, 10 to 60 minutes), not the original.

| # | Try | Pass when | WP | Owner result |
|---|---|---|---|---|
| 1 | Start kuulas, make a New project, close the window, start it again, open it from the start list | the project is listed with its age, size and tracks, and reopens as you left it | 29, 1, 15 | works (2026-10-19) |
| 2 | Double-click a `.kuulas` folder in Finder | it opens in the app | 72 | double-click on a .kuulas opens it (2026-10-19) |
| 3 | File > Import a WAV, an MP3 and a video file; also drag a file from Finder onto a track lane | each appears as a clip (the drop lands where you dropped it); a bad file gives a clear message, not a hang | 34, 1 | mp4 imported OK (2026-10-19); WAV, MP3, Finder drop and a bad file not reported yet mp3 drag works (2026-10-19) |
| 4 | Space plays and pauses; click the ruler to seek; play across a clip join; loop (Mod+U) | sound is clean and continuous, the cursor follows, nothing clicks at joins | 2 | works (2026-10-21); wanted: the loop button shows clearly when on (v26.10.20.16) |
| 5 | Split (B), mute (M), soft cut (Backspace: mutes in place, the gap stays; Mod+Backspace deletes), cut (X) with in/out marks (I, O), lift-cut (Alt+X), Tab to jump between clip edges | each does what its menu hint says; Undo (Cmd+Z) and Redo undo exactly one step | 5, 19i, 29 B, M, Backspace (mutes, as designed), I O X, Alt+X, Tab and Cmd+Z work (2026-10-19) |
| 6 | Copy, cut, paste (Cmd+C, X, V); look at the Clipboard tab | pasted clips land at the cursor; the entry stays listed | 46 |  |
| 7 | With the mouse: drag a range on the lanes, move a clip by its label strip, trim an edge, select with Cmd+Alt+click | each works without modifiers where the hint says so | 6, 54 Found a bug 2026-10-19: dragging a synced clip down to another track also moved its partner (BUGS 91); fix in progress not tested yet |
| 8 | Move a clip out of sync, then press R | the confirm dialog says what will move; confirming puts it back (a hole where the clip covered something is a known open point, BUGS 84) | 19a | R works in the cases tried (2026-10-19); edge cases may exist |
| 9 | Undo 20 steps and redo them; use Kumoa and Tee uudelleen in the History tab | state matches at each step | 29, 8 | Cmd+Z and Shift+Cmd+Z work (2026-10-19) |
| 10 | Close the app mid-edit (Cmd+Q), reopen the project | every edit is there | 29 | works (2026-10-19) |
| 11 | File > Export mix as WAV and as MP3; open the files in Quick Look and another player; Export all tracks | the files play, length and loudness look right | 11 | Cmd+E and Cmd+Shift+E work (2026-10-19); open: exporting only the in/out range or chosen tracks, MP3 settings, whether mute/solo count (BUGS 92, 93) |
| 12 | Help > Pikanäppäimet (cheat sheet); try the keys on the Finnish keyboard; Shift+Mod+K searches commands | no key needs AltGr or Shift+digit; search finds commands by typing | 5, 75, 81 |  |
| 13 | Zoom, change the panel, close and reopen | the view comes back as you left it | 35 | reopens at the cursor and zoom where it was closed (2026-10-19) |
| 14 | Click the clock (copies), double-click it (edit, jump), type +100 | works as the hint says | 76 | works; wanted: Final Cut style digit entry from the right (in progress) |
| 15 | Switch the language between Finnish and English | menus and dialogs change; no raw key names show | 33 | works (2026-10-21) |
| 16 | Open the menus: File, Edit, Clip, Track, Text, Playback, View, Help; hover over submenus | each is short enough to scan; hover opens submenus after a short delay | 74 | hover opens submenus, wanted faster (in progress) |

Not part of this list (they belong to later milestones): transcription, recording, automixing, cut candidates.
