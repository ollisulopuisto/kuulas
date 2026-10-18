## [v26.10.18.31] - 2026-10-18

- **Buses can be made now:** Track menu / palette "Group the selected tracks into a new bus" and
  "New empty bus", and "+ New bus…" at the end of the Bus choice in the inspector. (Nesting and
  clicking a collapsed bus are still to come.)
- Engine: loop playback (not reachable from the UI yet): the engine can loop a range with the
  same 15 ms crossfade as a skip, gap-free, and follows soft cuts. Nothing has been heard on a
  real device.
- Loudness targets: a track can have a target loudness (speech and narration -19, music -23 by
  default); "Match loudness" aims at it unless a target is given (the interface still sends -16
  until the monitoring panel lands). A per-track and mix loudness curve with integrated LUFS and
  true peak is available from the engine (`/api/loudness-curve`); the display comes later.

## [v26.10.18.30] - 2026-10-18

- Zoom keys: **Z** still toggles the close and wide view; **0** now always shows the whole edit;
  **F** fits the selection or the in-out range; **Alt+[** and **Alt+]** step back and forward
  through recent views. Nothing zoom-related sits on a modified Z any more (Cmd+Z and
  Cmd+Shift+Z are undo and redo).
- In and out points: **Shift+I** clears the in point, **Shift+O** the out point, and "Clear in
  and out points" (Markers menu and palette) clears both. The in and out commands are now in
  the Markers menu too.

## [v26.10.18.29] - 2026-10-18

- **P** plays from 3 seconds before the playhead (Hindenburg's key), to hear a spot again.
  The length is fixed at 3 s for now; the setting comes with project settings (WP27).

## [v26.10.18.28] - 2026-10-18

- Cut candidates: in the Candidates tab **Enter keeps** the candidate and **Backspace/Delete
  deletes** it, the same as everywhere else. K no longer does anything special there: J, K and L
  are the shuttle keys in every panel.

## [v26.10.18.27] - 2026-10-18

- Two internal building blocks for later features, not yet visible in the program: the maths for
  "align recordings by sound" (offset, drift, jumps, where to split) and the plan for which parts
  of each recording travel when an edit is sent for review or copied to another project.

## [v26.10.18.26] - 2026-10-18

- `kuulas import-nhsx <session.nhsx>` now needs no project folder: it makes `<session name>.kuulas`
  beside the session file. A missing session or a file given as the folder gives a plain error
  instead of a traceback.

## [v26.10.18.25] - 2026-10-18

- New command `kuulas import-nhsx <session.nhsx> <Name.kuulas>` imports a Hindenburg session into a
  project (tracks, clips, fades, gains, transcript words). Open the result with `kuulas open`.
  Until now the import only existed inside the program with no way to start it.

## [v26.10.18.24] - 2026-10-18

- kuulas remembers each project's view: zoom, scroll, lane height, waveform mode, follow mode, the
  current track, the sidebar tab, the play cursor and the in-out marks come back when you reopen the
  project. It is kept in a per-user file outside the project (no undo steps, the project is untouched).
  View menu and palette: "Reset remembered view".
- The command palette shows a "Recent" group (your last 8 commands, not navigation or undo) when
  the search box is empty.
- Panel sizes are not remembered because panels are not resizable yet.

## [v26.10.18.23] - 2026-10-18

- JKL shuttle: L plays forward and each further L goes faster (1x, 1.5x, 2x, 3x, 5x), J plays
  backwards the same way, K stops (in the Candidates tab K still means "keep"). A speed chip in the top
  bar shows the speed while it is not 1x; click it to return to normal play. Playback runs tape-style
  (pitch follows speed). The "." fast-listening key says it is not built yet. Hold-K slow scrub and
  K-tap 10 ms steps are not built. Not heard by a person (tested against a simulated engine).

## [v26.10.18.22] - 2026-10-18

- Narration placeholders: T puts script text on the current track at the play cursor, with a live
  "14 words, about 6 s" estimate; it shows as a dashed box with the text. Enter or a double-click
  edits it (the length follows the text until you set it by hand). A placeholder moves with ripple
  cuts on its own track. Narration menu ▸ "Record or import a take" replaces it with a real clip in
  place; later material on the sync group shifts by the difference, in one undo step. File menu:
  export the script as text or Markdown (each placeholder with its time, estimate and 20 words of
  context either side). Exports warn how many placeholders were skipped. Shift+Alt+T deletes one.
  Not built: the "to record" row in the transcript, and the browser file picker for takes was not
  tried by a person.

## [v26.10.18.21] - 2026-10-18

- Playback engine: it can now skip stretches while playing ("as if cut") with a 15 ms equal-power
  crossfade at each join, and it can play at tape speeds (0.25x to 5x, forwards or backwards,
  pitch follows speed). The cut-candidate preview (Shift+Space) now uses one play with a skip list
  instead of two plays and a timer. Pitch-kept fast listening (1.1x to 3x) is not built; asking for
  it says "not available yet". NOT yet listened to by a person: how the crossfade sounds on speech,
  and CPU use at high speeds on the Mac (the tests pull audio blocks from a fake output).

## [v26.10.18.20] - 2026-10-18

- Markers, regions and chapters. M adds a marker at the play cursor (a pennant on the ruler),
  Alt+M turns the in-out range into a region (a bar), Shift+Mod+Right/Left jump to the next or
  previous marker, Shift+Alt+M deletes. The new Markers tab lists them (name, time, kind, length)
  with jump, rename, a "Chapter" toggle and delete. Markers move with the audio when you ripple-cut
  or insert across all tracks (a cut that touches only some tracks leaves them alone).
- File menu: export chapters as text (`00:00:18 Title`) or as Podcasting 2.0 JSON, and export the
  regions as separate audio files (one job with progress; names like `01 Region 1.wav`, never
  overwriting an existing file). Two chapters on the same frame refuse to export with a message.
- Older kuulas versions keep the markers but do not move them on a ripple (a wrong position, not
  lost data).

## [v26.10.18.19] - 2026-10-18

- G sets a fade on the clip under the play cursor (the nearer end; the other fade gives way if
  they would overlap). One undo step.
- Track menu and palette: "Match loudness" sets the selected clips (or all clips of the current
  track) to -16 LUFS, shows "Measuring N clips…" while it works, then "Matched N clips · M skipped
  (silent)" with Undo. (The -16 target is fixed for now; there is no project loudness setting yet.)
- File menu and palette: export subtitles (SRT or VTT) and the transcript as text or Markdown.
  Disabled when there is no transcript. In the desktop window these use the browser download, not
  the native save dialog yet.
- Mod+F: a find bar in the transcript. Accent-insensitive ("paiva" finds "päivää"), shows "2 / 5",
  Enter and Shift+Enter step with wrap-around, the transcript and the play cursor follow.
- Fixed a test that failed now and then: two exports one second apart differ in the clock time
  stored in the WAV header; the audio was always identical.
- Building blocks: speaking time, turns and words per minute per speaker; the transcript as text.

## [v26.10.18.18] - 2026-10-18

- Match loudness (backend): a session command brings chosen clips to a target level
  (-16 LUFS by default) by setting each clip's gain, measured in 60 s pieces off the session lock,
  as one undo step; silent clips are skipped and reported. No key or button yet.
- Fade at the play cursor (backend, the G key): sets the fade in or out of the clip under the cursor
  from the cursor position, shortening the other fade if they would overlap.
- Building blocks: finding words in a transcript (accent-insensitive, multi-word) and subtitles
  from a transcript (SRT and VTT with line breaking, speakers and gaps).

## [v26.10.18.17] - 2026-10-18

- Candidates panel: a "Candidates" tab with the counts (N open · N cut · N kept), a "Find
  candidates" button, and the list in time order with kind (silence, filler, retake, marked),
  the quote or reason and the state. `]` and `[` step through (the play cursor and timeline follow);
  open candidates show as faint bands on the affected lanes and a "cut? 2.4 s" flag in the ruler.
  In the tab: Enter deletes the stretch (soft cut, gap kept), the "Cut and close gap" button
  ripples, K keeps it (it never comes back). D marks your own candidate at the in-out range
  or between two presses at the play cursor. Shift+Space previews "as if cut": it plays before the
  stretch, then after it (two plays with a short timer; not yet listened to by a person). Not built:
  the overview strip's candidate ticks, and a help topic.
- Building blocks: nudge steps (1 ms, 10 ms, 100 ms, 1 s), the list of recordings the edit
  does not play (for the clip bin).

## [v26.10.18.16] - 2026-10-18

- Cut candidates (backend, no panel yet): kuulas can propose cuts and remember your decisions.
  It finds long pauses (1.5 s and over, leaving 0.5 s each side), filler words and hesitations in
  English and Finnish (öö, ää, niinku, tota ...), and repeated words or phrases (retakes),
  skipping anything already muted, gated or cut. Each proposal is open, cut or kept; kept ones
  never come back; your own marks stay. Accepting one is a soft cut on that speaker's track (a
  pause: on every track of the group) in one undo step, or a ripple cut if you ask. They are
  stored in the project so decisions survive edits and undo; older kuulas versions keep them
  untouched. Read them at `/api/candidates`. Thresholds are first guesses, not tuned on real
  recordings, and Whisper often drops "um"s, so fillers will be fewer than you expect.

## [v26.10.18.15] - 2026-10-18

- History panel: the History tab lists every step of the edit, newest first, in pages (it can
  hold thousands), with the session markers as dividers ("Opened today 19.30", "Closed yesterday
  22.14"), the current step highlighted, steps you can redo dimmed and abandoned branches dimmed
  and indented. Pick a step with the mouse or Up/Down and press Enter (or double-click) to restore
  it: that adds a new step and nothing is lost. Undo or redo across a session marker says
  "Undid a step from yesterday: <step>". Times are Helsinki time, the tooltip names the zone.
  Not built: hover preview of a step, pinned steps, and step icons.
- The history route can return pages (`/api/history?limit=...&before=...`); undo and redo
  answers say whether they crossed a marker.

## [v26.10.18.14] - 2026-10-18

- Inspector "Source" section: for a selected clip it shows how much of its recording is used
  ("Used 62% · 3 parts"), a small map of the whole recording (used solid, cut hatched, unused
  outlined, this clip boxed), "Part 2 of 3", and a list of the other clips from the same
  recording that you can click to jump to. Collapsed by default.
- X on selected transcript words now copies them to the clipboard before cutting (the toast says
  "in the clipboard", or "NOT copied" if the copy failed while the cut still happened).
- The README is up to date (what works, how to run and test, what has not been verified).
- Building block: measuring how loud a clip is (read in 60 s pieces) and the gain that would
  bring it to a target level.

## [v26.10.18.13] - 2026-10-18

- Transcript panel: the dock under the timeline shows the transcript as one paragraph per
  speaker turn, follows playback, and a click on a word moves the play cursor there. Shift+click,
  a drag or Shift+arrows select words. A pop-up offers "Delete these words on <speaker>"
  (Backspace: mutes only that speaker's track, keeps the gap, one undo), "Cut on all tracks"
  (X: ripple, closes the gap) and "Correct" (one word). While words are selected it says what else
  the cut would remove: "Also removes 3 words from Ville and 1.2 s of Pekka", marks those words,
  and hatches the affected stretch on the timeline. Long transcripts stay fast (an hour of words).
  Note: X in the transcript does not copy to the clipboard yet.
- Importing several files: after a drop or pick a small panel says what happened ("4 files
  imported as 4 tracks, in sync") with "One after another instead" and Undo; failed files are
  listed with the reason. A drag shows a preview where the files will land (below the tracks:
  new tracks at the start; on a lane or the ruler: from that time). Order and track naming
  defaults are remembered. Dropped folders are searched for audio and video files.

## [v26.10.18.12] - 2026-10-18

- Importing several files has options on the server side: place them side by side (by the
  recorders' clocks) or one after another on one track, ordered as given, by file name
  (take2 before take10) or by recording time, tracks named after the file or the person, and a
  start position. The default is exactly what it was. No window for the options yet.
- Two read-only questions the window can ask: what else a transcript cut would remove
  (the crosstalk preview) and where a recording is used (used, cut and unused stretches, "part 2 of
  5"). Both leave the project untouched.

## [v26.10.18.11] - 2026-10-18

- Clipboard with history. Mod+C copies the selection (or the in-out range); X now copies
  and cuts; Mod+V pastes at the play cursor on the same tracks and moves later material
  right (the whole sync group follows when group editing is on); Alt+Mod+V overwrites;
  Shift+Mod+V pastes on the current track. Backspace never touches the clipboard. A
  Clipboard tab in the sidebar lists everything you copied (newest first, with a name like
  "Anna +1 · 0:12"), with pin, rename, delete and "Paste again". The history is saved on
  this computer and works between projects (media are matched by content; missing ones are
  reported). One undo undoes a whole paste. Not tried by a person yet: overwrite and
  current-track paste in the window, and pasting into another project's window.
- Restoring a soft cut joins the pieces back into one clip where nothing differs.

## [v26.10.18.10] - 2026-10-18

- Clips can have a name of your own (kept through splits and trims, one undo step,
  empty means automatic). No window for it yet; F2 renames tracks.
- Building blocks, not yet visible: joining adjacent pieces of a clip back together,
  where a clipboard paste would land (insert or overwrite, mapping tracks), safe file
  names for exported regions (Mac, Windows and Linux rules, Finnish letters kept), and a
  Safari pinch-zoom gesture helper for the future desktop window.

## [v26.10.18.9] - 2026-10-18

- Contextual help: F1 opens a docked help panel for whatever has focus (timeline, a
  clip, a track, a bus, the transcript, history) with search over help topics and
  commands, a "Show me" button that rings the control, and the keys it names read from
  your own keymap (a remapped key shows as remapped). Help menu: "Help for this". `?`
  still opens the shortcuts sheet. Six topics in English and Finnish; more can be added
  as plain files. Welcome and tour screens exist as a sketch in the prototype only.
- Muting and unmuting is now exact: the 30 ms smoothing at the edge of a muted stretch is
  worked out while mixing instead of being written into the neighbouring clips, so
  unmuting (or undoing a soft cut) restores the original sound with no dip. Old projects
  that stored such fades sound as before.

## [v26.10.18.8] - 2026-10-18

- The editing keys work in the editor: B splits at the play cursor (Shift+B on all
  tracks), Backspace or Delete is a soft cut (mutes the selection or the in-out range
  in place, keeps the gap, one undo brings it back), X cuts and closes the gap (Shift+X
  on this track only), N mutes, Shift+M mutes the track, Shift+S solos it, E turns group
  editing on or off (an amber chip shows when it is off), Q and W trim to the play cursor,
  Mod+Left/Right nudge by 10 ms, Mod+A selects all, Shift+Mod+Up/Down change clip gain in
  0.5 dB steps. Each shows a toast with Undo. Copy, paste, fade at the cursor and the
  lift-cut are not built yet.
- Building blocks, not yet visible: clipboard entries and their history (what a copy
  keeps, pinning, pruning, saving as text); the fast-listening speed state (1.5x default,
  1.1 to 3.0 in steps of 0.1); a check that the English and Finnish texts agree
  (`uv run python scripts/check_locale.py`).
- Tests that failed now and then when the computer was busy are steadier.

## [v26.10.18.7] - 2026-10-18

- Auto-Silence's closed stretches now show in the editor: a dim veil over the lane,
  a flat waveform under it, a small tick at each edge and the words "Mic closed" when
  there is room. Double-click a stretch (or run "Open this stretch" from the Track menu
  or the palette) to reopen it as one undo step. View has a "Show gates" switch. The
  switch is global for now, not per lane.
- Building block, not yet visible: a placement plan for importing several files
  (side by side or one after another, by file name or recording time, track names from
  file or person).

## [v26.10.18.6] - 2026-10-18

- Keyboard layer: every key is data, so you can change it. Press `?` for the cheat
  sheet (grouped, searchable, shows your own keys, with import, export and reset of a
  key file); conflicts are reported instead of silently accepted. Keys that exist today:
  Space, Z, Shift+Z, =, -, Mod+Z, Shift+Mod+Z, Mod+I (import), Mod+K, ?, F2, F6,
  Home, End, arrows, I and O. Many more are listed but marked "planned" until the
  commands exist (split, cut, copy and paste, trim, mute, solo, sync, candidates).
- Command palette (Mod+K): a docked panel over the sidebar, no dark overlay, the
  timeline stays live.
- An in-window menu bar (File, Edit, Track, View, Help): items that cannot apply are
  greyed but stay visible with their shortcut, a remapped key shows at once, hovering
  an item shows a hint and its key. While you hold Shift or Alt, items and hints swap
  to what that modifier would do, like the Option key on a Mac. First cut of the look.
- Finnish keyboard: `[` and `]` work by key position; AltGr is not treated as Ctrl+Alt.
- Also: `uv run python scripts/check_isolation.py` and the gate tooling (earlier).

## [v26.10.18.5] - 2026-10-18

- Auto-Silence no longer cuts your clips into pieces. It now records, for each
  track, the stretches where the mic is closed (a "gate"); clips stay whole and the
  gate can be reopened stretch by stretch. Playback and export apply it with a short
  30 ms fade at each edge, and everything that asks "is this audible?" (music report,
  transcript, usage, edit points, onsets) treats gated stretches as silent. Running
  Auto-Silence again replaces the gate instead of piling up. On a busy 4-mic test
  session the state is about a fifth of the size it was with clip pieces.
- Project format version 3. A project becomes unreadable to older kuulas versions
  only once it contains a gate (they would play the closed mics). Projects without a
  gate stay readable by old versions. Old projects open unchanged.
- Not visible in the window yet: the gate bands and the "Open this stretch" action.

## [v26.10.18.4] - 2026-10-18

- Desktop app (first cut): `kuulas` with no arguments opens a native window with
  your recent projects; `kuulas open <project> --window` opens one project in a
  window. Needs the extra: `uv sync --extra desktop`. In the window the Import
  button uses the system file dialog and dropped files are linked in place, not
  uploaded. Not yet checked by a person: how the page looks in the window, closing
  it, the launcher buttons, and anything on Windows or Linux.
- A GitHub Actions workflow (`.github/workflows/ci.yml`) runs the checks on Mac,
  Windows and Linux. It cannot run until you add a repository secret
  `PODCAST_READ_TOKEN` (read access to the podcast repo, which kuulas still needs
  for speechmix and nhsx) and push.

## [v26.10.18.3] - 2026-10-18

- Design only (open `docs/design/prototype/index.html`): a "Cuts explained" screen
  showing Delete, Cut, Lift-cut, Mute, Auto-Silence, Restore and Put back side by
  side with before and after, and a "Nested buses" screen (an "All speech" bus
  holding interviews). Eight bus colours now, with letter badges (A, A1, A1a).
  Nothing of this is built into the editor yet.

## [v26.10.18.2] - 2026-10-18

- The editor is much roomier by default ("comfortable"): lanes 80 px tall,
  larger text, bigger buttons. "Compact" keeps the old dense look; switch in the
  new View menu (bottom right), which also holds Animation (full, subtle, off).
- Calmer at rest: about 22 controls instead of 51. Gain and pan show for the
  current track and on hover; key hints show on hover; the inspector keeps Level
  and Sync open and folds the rest.
- Buses are one-line rows above their tracks (tracks indented), with gaps
  between groups, and a bus with one track merges into the track's own header.
- Clicking anywhere in the lane area, including bus rows and gaps, moves the
  play cursor.
- Clips are named by width ("Anna", "Olli 3", "Olli 3 · 1:20–3:20", then the first
  words); clips from the same recording get corner brackets and ticks in the
  overview.
- Double-click or Shift+Enter on a slider or number field flips between the
  default and your last custom value (one undo step each time; Alt resets).
- Gentle animation cues (after undo, new tracks, and so on) that follow the
  system "reduce motion" setting.
- Layout adapts to window width (checked at 1280, 1440 and 1920).
- Still to build: Compare (A/B), importing several files with options, the
  crosstalk preview in the window, nested buses, the clipboard history, and a
  Track section in the inspector (a merged one-track bus has no pan control
  until then).

## [v26.10.18.1] - 2026-10-18

- Music tags can be corrected: title, artist, composer, publisher and ISRC are
  editable per recording, as one undo step, and the music report shows the
  corrected values. An empty value blanks a tag the file had; removing the edit
  brings the file's own value back. (No window for it yet.)
- Building blocks, not yet visible in the app: the JKL shuttle speeds (L, J, K
  and the slow scrub), the arithmetic for Auto-Silence's merged gate ranges
  (merge short gaps, add, remove, ripple), and level matching for A/B
  comparison (the louder side is turned down by the loudness difference).
- Tooling for the helper agents: a gate every agent must pass before reporting,
  a script that checks each test file passes on its own, and a quota tracker
  for the OpenCode Go plan.

## [v26.10.17.9] - 2026-10-17

- Building blocks, not yet visible in the app: a typed-time parser for the
  "Spot" dialog (`1:02:03,5`, `2:03`, `62.5`, `+120` ms, `-0.5s`; Finnish decimal
  comma works) and a diff that reports which stretches of a recording were cut
  or restored between two history points, whatever the clips' arrangement on
  the timeline.

## [v26.10.17.8] - 2026-10-17

- The editor has a designed look: a calm dark and light theme (follows the
  system, switch with the theme button), speaker colours on clips, status bar
  with key hints, and a Finnish and English interface.
- Buses show as group headers above their tracks, each with its own colour
  stripe and letter badge.
- Clips use one visual language: muted clips are hatched, placeholders have a
  dashed outline, sync is shown with a link mark and offset, damaged media in
  red, and several files on one track alternate in tone with a small file mark.
- Behind it: one central list of every visual signal and colour, so themes can
  be added later as data. See `docs/design/GUI-DESIGN.md`; open
  `docs/design/prototype/index.html` for a clickable prototype of the whole
  intended interface (not all of it is built yet).
- Also in this version: the pre-review gate and quota tracker for the helper
  agents (`scripts/agent_gate.py`, `scripts/go_quota.py`).

## [v26.10.17.7] - 2026-10-17

- The editor window works as a first version: waveforms for each track, track
  and bus headers, and an inspector for the selected clip.
- Zoom with = and -, switch between a close and a wide view with Z, and use the
  overview strip, follow modes and F6 to move between panels.
- Import audio by drag-and-drop or the file picker. If the connection to the
  server drops, the window says "reconnecting…".
- Fixed: `kuulas open` could not serve the live feed without a WebSocket
  library; it is now installed with kuulas.
- Not yet tried by a person: playing audio with Space from the window.
- Undo and redo now return the editor context of the step, and opening or
  closing a project leaves a marker in the history so "undid a step from
  yesterday" can be shown. (WP8, first half; no history panel yet.)

## [v26.10.17.6] - 2026-10-17

- Building block for editing in sync: the rules that find which clips on other
  tracks play the same stretch of a recording, and which tracks or clips a
  time-shifting edit should take along. Not yet used by the edit commands, so
  nothing changes in the app yet.

## [v26.10.17.5] - 2026-10-17

- Building blocks, not yet visible in the app: a chapter-list formatter (plain
  `hh:mm:ss Title` lines or Podcasting 2.0 JSON) and a narration-length
  estimate (words to frames at 2.3 words per second, at least one second).

## [v26.10.17.4] - 2026-10-17

- Tracks now have a kind (speech, speech-mix, music) and a speaker. Tracks of
  the same speaker count as one voice, and a recording of everyone (Zoom or
  phone) counts as "someone is talking" without being ducked itself.
- "Duck music" lowers every music track under speech with the music-bed curve,
  as ordinary track automation you can edit.
- Transient onsets (for the Tab key) are measured once per file in 60 s
  pieces and cached; no whole file is held in memory.
- The History list can be read in pages, and long histories stay fast
  (tested at thousands of steps).
- Music report: a speaker with one muted track no longer loses the others.

## [v26.10.17.3] - 2026-10-17

- A manual transcription test (`uv run --extra transcribe pytest -q
  tests/manual/test_transcribe_smoke.py`) checks that local transcription
  returns words with times in the project's units, using the machine's own
  speech voice. It is not part of the normal test run.
- Installing the transcription extra now keeps `av` below version 19, which
  faster-whisper 1.2.1 does not work with.

## [v26.10.17.2] - 2026-10-17

- Music report: it can now be fetched from the app (`GET /api/music-report`
  as JSON, CSV or HTML), and building it no longer blocks editing. CSV cells
  that start with `=`, `+`, `-` or `@` get a leading apostrophe so Excel does
  not run them as formulas.
- People and interviews can be deleted, as one undo step. Deleting a person
  also removes them from interviews, media and speaker maps, and undo brings
  all of it back.
- A damaged working file can be rebuilt from its original, checked by content
  hash. (The playback engine's "damaged" notice is not yet cleared by a
  rebuild.)
- Decoded audio for playback now counts against the memory budget with the
  other caches.
- The test suite can run where the default Numba cache folder is not writable.

## [v26.10.17.1] - 2026-10-17

- Music report times are whole seconds, and partial seconds round up: a 0.4 s
  sting is reported as one second. The out time is the in time plus the
  duration, so the three columns always agree.

## [v26.10.16.15] - 2026-10-16

- Music report: lists every piece of music the programme actually plays, with
  title, artist, composer, publisher, ISRC, in and out times, duration, and
  whether it plays under speech ("background") or on its own ("featured").
  Music that is muted, ducked away or under a muted speaker does not count.
  Output is a semicolon-separated CSV that Finnish Excel opens correctly, and
  a printable HTML table, in English or Finnish. Pieces with no title or artist
  are flagged in the report.
- Title, artist and the other tags are read from the music files when they are
  imported.
- The tests no longer depend on the machine's language or on the order they
  run in.

## [v26.10.16.14] - 2026-10-16

- Export: mix the whole edit, a selection, or each track as its own aligned
  file (dry or as heard) to WAV, FLAC or MP3, with optional loudness
  mastering. Export names are versioned and never overwrite; an unchanged
  export is skipped and points at the earlier file. Settings are remembered
  per project and each export is a history entry. Cancelling removes partial
  files. Available through `POST /api/export`; there is no export dialog yet.
- Background jobs: transcription runs as cancellable local jobs
  (faster-whisper) that yield to playback and user input, with progress in
  `GET /api/jobs` and on the live channel. A newer transcript is never
  overwritten; the job reports a conflict instead. Colab transcription is not
  available yet.
- Hindenburg sessions (`.nhsx`) can be imported: tracks, regions with gain,
  pan, mute and fades, and the transcription words with speaker labels.
  Missing or unreadable audio is reported per file and the rest still
  imports. Importing only; exporting back to Hindenburg is not built.
- Portable projects: linked media is found again on another machine through
  package-relative paths, media folders and learned path rewrites, and every
  candidate is checked by content hash. Relinking one file fixes the others
  under the same folder. Project data gains path fields (schema v3,
  migrated automatically).
- Projects can now report every used recording range in its original media
  clock, including ranges heard through excerpts.
- Muted and deeply ducked passages are marked inaudible; nearby uses on the
  same track are combined for downstream music reports, series tracking and
  change comparisons.

## [v26.10.16.13] - 2026-10-16

- People and interviews are now part of a project, added, edited and undone
  like any other change.
- Say whose voice is on a mic file, or map a mix's speaker labels to people;
  correcting the map never changes the transcript text.
- Files imported together are offered as one interview, in the same undo
  step as the import.
- Everything a person said can be listed, with recording ranges, in a project
  or across several.
- Series folders store people and interviews as one small file each, so sync
  conflicts stay local and are reported.
- Project format version 2: older projects are upgraded automatically after a
  backup, and older kuulas versions can still open them.

## [v26.10.16.12] - 2026-10-16

- The editor window's text and formatting layer exists (`ui/i18n.js`), so
  nothing built on it needs untranslated text: English and Finnish from the
  same catalog the server uses, plurals by language rules, Finnish decimal
  comma ("−2,5 dB", "12:34,567"), absolute times in Helsinki time with the
  zone named ("19.45 (Helsinki)", "7:45 pm Helsinki"), key names per
  platform and language (⌘ on a Mac, Ctrl elsewhere; "Välilyönti" in
  Finnish), and switching language without a reload.
- `GET /api/locales/<lang>` serves a language's catalog.
- On a Mac the language now follows the system's language list, not the
  Terminal's `LANG`, so a Finnish Mac gets Finnish messages even when
  Terminal says `en_US`. `LC_ALL` and `LC_MESSAGES` still override.
- Checks that keep it so: every key the UI uses must exist in the English
  catalog, and no UI code may put a literal text into a visible property.

## [v26.10.16.11] - 2026-10-16

- `kuulas open <folder>` opens a project (creating it if it does not exist)
  and serves it on this computer only (127.0.0.1, any free port), then opens
  the browser. There is still no editor window: the page says so, in
  English or Finnish by the browser's language. `--port` and `--no-browser`
  are available.
- The HTTP API the editor window will use exists: project state, edits,
  commands, undo/redo, history, restore, importing by path or by upload
  (with a per-file report of what came in, what failed and why), waveform
  tiles the browser caches, transcript words, transcript import, word
  correction and playback control.
- A live channel pushes what happened instead of the UI asking: the heard
  playback position, state-changed notices and audio warnings.
- Restoring an earlier step now adds a new step (it can be undone) instead
  of moving back; correcting a word of a transcript is one undo step.
- Errors reach the UI with a key and a translated text; the text follows
  the browser's language. An edit round trip on the hour-long, 1,204-clip
  project takes about 14 ms (budget 50 ms).

## [v26.10.16.10] - 2026-10-16

- Waveform overviews are computed once per recording at import, at five zoom
  levels; edits never recompute them.
- Auto-Silence and automix no longer re-read audio after an edit: each
  recording's levels are measured once and cached.
- Undo and redo of recent steps are instant (the last 64 states stay decoded).
- One memory budget (2 GB by default) for all caches, spilling to disk;
  cache hit rates are logged.
- Playback reads no longer touch the database or re-check files, so a
  changed or slow drive cannot stall the audio.

## [v26.10.16.9] - 2026-10-16

- Importing is fail-soft. One bad file no longer sinks a batch: each file
  gets its own result with the reason, and empty, unreadable, audio-less
  (video) and hung-decoder files are refused with a clear message.
- Truncated or damaged files import as far as they decode and are marked
  partial ("0:41 of 0:58"). Silent files are flagged; files with more than
  two channels are mixed down to stereo with a warning; a recorder start
  time over 24 h is ignored; RF64 files over 4 GB are read correctly.
- Free disk space is checked before decoding. A full disk or an unplugged
  source drive removes the half-written file and says how much space is
  needed or which drive vanished.

## [v26.10.16.8] - 2026-10-16

Playback exists, though there is still no app to press play in (the HTTP
API comes next). Not yet tried on real speakers: run
`uv run pytest -q tests/hardware -s` on the Mac and on Windows before
relying on it.

- Plays the project through the computer's default output (CoreAudio on a
  Mac, WASAPI on Windows), with the same mix as export. Play from anywhere,
  play a selection and stop at its end, stop, jump while playing; an edit
  made during playback is heard within one buffer (about 21 ms).
- The playhead position reported is what you are hearing, not what was
  just computed, so the display does not run ahead of the sound. Stopping
  leaves the playhead where you heard it.
- Audio problems cost a moment of sound, never the session: a block that
  fails plays as silence and is reported; a stream that dies or freezes
  (headphones unplugged, Bluetooth dropping) is reopened on the current
  output and playback pauses with a message; if playback falls behind, the
  buffer is doubled and a "playback is struggling" message appears instead
  of silent stuttering. A device that cannot play the project's sample
  rate gets converted audio, with a note; exports are unaffected.
- A recording whose stored audio is damaged in one place plays silence
  there, plays normally elsewhere, and is marked damaged with a message
  naming the file and the time. (Rebuilding it from the original is not
  offered yet.)
- Reference renders of eight small test projects now pin down what the
  mixer sounds like; any future playback engine must reproduce them.
- New dependency: soxr (sample-rate conversion for playback only).
- Not yet: following a change of the default output while the old one
  still works (picked up at the next play after half a minute idle).

## [v26.10.16.7] - 2026-10-16

There is still no app to open; this is the layer the app will talk to.

- Opening a project now gives one place that every change goes through:
  edit, undo, redo and jump to any earlier step, each change saved before it
  is acknowledged. Reopening after a crash resumes at the last edit.
- Importing several files at once puts each on its own track (mono as
  speech, stereo as music) as one undo step. Files imported together are
  treated as recorded together: placed by the recorder's own clock when the
  files carry one, and grouped in sync.
- Transcripts can be set and corrected as undoable steps; deleting words
  cuts the same stretch from every track.
- Auto-silence (optionally for chosen tracks), automix, relink and
  consolidate are available as project commands.
- Clicking solo through the tracks is a single undo step, and mute clicks
  on one track merge, instead of one step per click.
- Fixed: importing the same audio twice in one batch could clash while
  both copies were being encoded; the second now waits for the first.

## [v26.10.16.6] - 2026-10-16

- Sync groups now belong to the recordings, not to clips: marking clips in
  sync puts their whole files in the group, every edit of the project sees
  the same groups, and marking or unmarking undoes like any edit. Resync
  works as before.
- Recording times (transcript words, recorder start times, sync offsets)
  are kept on an exact clock that does not depend on the project's sample
  rate, so changing the rate later will not shift a word or a sync point.
- Audio files at an unusual sample rate the exact clock cannot hold (for
  example 37.8 kHz) are refused at import with a message saying to convert
  them first. Every common rate, 8 to 192 kHz, works.
- Projects from earlier development builds keep their sync groups when they
  are upgraded.

## [v26.10.16.5] - 2026-10-16

The project format kuulas will keep (format version 1). There is still no
app to open; this is what the app will save into.

- A project is a `Name.kuulas` folder: one database for every edit and its
  history, the audio beside it, rebuildable caches, and automatic backups.
- Transcripts, media and their names are shared by every edit of a project:
  a transcript correction made in one edit shows in all of them, and can be
  undone, unless someone has changed the same transcript again since (then
  kuulas refuses rather than throwing that change away).
- Every history step records who made it and on which computer, with an id
  that stays unique when a copy of the project comes back from a reviewer.
  Steps can be named (checkpoints).
- Opening a project that is open on another computer (via Dropbox or
  similar) opens it read-only, instead of corrupting it. A project left
  locked by a crash is taken over after two minutes, with a warning.
- Automatic backups every 10 minutes while there are changes: the last 12,
  plus the last one of each day for two weeks, in the project's `backups/`.
- A project made by a newer kuulas opens and keeps everything this version
  does not understand; one that needs a newer kuulas is refused with a
  message saying which version made it.
- Projects made by earlier development builds are upgraded on open, after a
  backup copy of their database.
- `kuulas info <folder>` shows a project's format, sizes, media (linked,
  copied, missing) and backup count.
- Waveform data is a cache: deleting `caches/` is safe; it is rebuilt.

## [v26.10.16.4] - 2026-10-16

- Error messages are in Finnish as well as English. kuulas follows the
  language of the computer (Finnish if it is set to Finnish, English
  otherwise). Edits that cannot be made, missing media, and transcription
  that needs an install all say what went wrong in that language.
- Messages from the speech pipeline (plug-ins, mastering, bleed removal) are
  in Finnish too.
- The app's own screens are still English until the interface is translated.

## [v26.10.16.3] - 2026-10-16

- Analysis of several speech tracks (what decides who is talking, for
  Auto-Silence and automixing) now runs one track per processor core. The
  result is the same as before, only faster on a multi-track project.

## [v26.10.16.2] - 2026-10-16

- Solo now works the way a mixing desk does: soloing a track hears it even
  when it is muted, and soloing another track unsolos the first. Hold the
  additive modifier to solo more than one track. A muted bus still silences
  its tracks, even when they are soloed.

## [v26.10.16.1] - 2026-10-16

First working core of kuulas. There is no app to open yet; this release is the
engine the app will be built on.

- Projects of tracks, clips, buses and a master, changed only through named
  edits: move, trim, split, ripple delete with crossfades, mute, fades, gain
  and pan, automation, sync groups, and selection-wide edits.
- Every edit is saved to disk before it counts, and undo keeps every branch,
  so nothing is lost after a crash or an undo.
- Import of audio files and video (audio track only), kept as lossless FLAC
  where the source allows it, with files identified by content, so renamed or
  moved files are recognised.
- Auto-Silence and automixing, using the podcast pipeline's speech detection.
- Transcript words that follow the audio, and cutting audio by deleting words.
