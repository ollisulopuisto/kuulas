## [Unreleased]

## [v26.10.25.1] - 2026-10-25

- **No hand-typed key names in user text.** User-visible text looks up shortcut keys from the active keymap at render time, ensuring user remappings and platform modifiers are reflected accurately and stale key instructions are eliminated.
- **Move tracks: drag a header's handle, or Track > Move track up / down.** A small dotted handle at the left of each track header (shown on hover and on the current track) drags the track to a new place; the commands do the same one step at a time. The clips and their times stay as they are, one undo step. The average-loudness text moved to the level row of the header, so it no longer covers the track's name.
- **Right-click menus for more things, with their keys.** The track and bus header menus now show each command's key, like the timeline menus. The clip menu starts with Split / Delete / Mute / Fade / Group, then Clipboard and Paste, and has Match loudness instead of the nudge and trim steps (those only make sense on a key repeat). The track menu offers Move up / down, Select all on this track and Focus, and either Remove from bus or Group into a bus, not both. New menus: a marker flag or region bar on the ruler (Delete marker, Previous / Next marker; the marker is selected first), a point on a clip's volume line (Delete volume point, Clear volume line, also in the Clip menu), a point of a track's ducking curve (Delete ducking point, Clear ducking curve; also in Track > Auto), a narration placeholder (Take, Edit, Delete), transcript words (right-click a word that is not picked and it becomes the pick; Delete, Cut, Remove, Correct, Mark as a candidate), a Clipboard row (Paste, Preview, Send to the other window, Move), and the ruler has Delete marker and Previous / Next marker. A range also offers Mark as a candidate.
- **A cart clip is trimmed when you stop it early, and played at the level of the voices.** While a take records, a clip played from the cart is put on the timeline for as long as it was actually heard (stopping it, playing another one, or ending the take shortens it; the recorded files are never touched). It plays at about the level of the voices (a three-second figure from the recorder's levels, or the project's reference level when nobody has spoken yet), never above the clip's own peak, and the same gain is stored on the logged clip. The Clipboard has a small trim (dB) for the cart. Not tried with a microphone.
- **Automation snap also for edge trims and clipboard drops.** Hold Cmd (Ctrl) while dragging a clip's edge, or while dropping a clipboard entry on the timeline, and it snaps to the same volume-automation points and closed-stretch edges as a clip move does, with the marks along the top. Not seen on screen.
- **A slim recording bar with Stop and Add marker.** While a take records and the big record view is hidden, the toolbar shows a Stop button (the same stop gesture you chose in the record view) and an Add marker button beside the "Recording" chip. Not seen on screen, not tried with a microphone.
- **Play the other tracks while recording (off by default).** The record setup has "Play the other tracks while recording" and "Recording delay (ms)". With it on, every track the take does not record onto plays from the take's start (use headphones: the microphone hears them otherwise), and the take's head is cut by the delay when it lands, so it lines up with what you heard (the recorded file is never changed). The delay is a number you set by ear for now; measuring it is not built. Known limit: a clip on a recorded-onto track that keeps the mic open still sounds. Not tried with a microphone or real headphones.
- **M acts on the Auto-Silence portion under the cursor, also for a grouped clip and with nothing selected.** Selecting a clip selects its whole group, so M used to mute the entire parent clips; now the portion under the play cursor on the current track (closed or audible) becomes its own clip and is toggled, and the rest of the group is left alone. With no clip selected, M uses the current track's clip under the cursor.
- **Clip borders no longer look like the waveform.** The border is a neutral grey that is at least 1.6 times apart in contrast from every track colour's waveform, in both themes, so a clip's edge and its sound are easy to tell apart.

## [v26.10.24.3] - 2026-10-24

- **M toggles both kinds of Auto-Silence portion.** An audible opening between two closed stretches now becomes its own muted clip, instead of muting the parent. A closed stretch becomes audible. The edited portion is selected, independent of its parent's group, and stays outside later Auto-Silence runs, including after moving it. Undo restores the implicit portion.
- **Drag a dotted boundary to make that portion explicit.** Both audible and closed portions can be trimmed this way. Clicking a boundary without dragging only positions the cursor.
- **Double-click keeps its specialized actions.** It edits envelope points near the gain line, locates missing media, and edits placeholders. It no longer opens Auto-Silence stretches; use M to toggle a portion.

## [v26.10.24.2] - 2026-10-24

- **Follow and Auto-Silence edits stay on the intended target.** Scrolling the transcript unlocks follow through playback updates. M on a clicked implicit region materializes only that region, including inside a clip group or overlap; dragging either border materializes and trims only that region, including borders at the parent clip edges.

## [v26.10.24.1] - 2026-10-24

- **Auto-Silence belongs to the clips it measured.** Moving another clip into the same timeline area no longer silences it. Auto-silenced ranges stay implicit until changed; pressing M or dragging a range edge makes only that portion a real clip. Clip borders use a neutral color distinct from the waveform. During playback, manually scrolling the transcript unlocks follow until Follow is pressed.
- **You can copy the text of a toast.** Select it with the mouse and press Cmd+C (Ctrl+C); that copies the text, not the clips. A toast stays open while the pointer is on it or text in it is selected.
- **Level blocks is a side panel, so you can keep editing while it measures.** It docks over the sidebar like Auto-Silence's panel (opening one closes the other). If you edit the project while it measures, or after it has shown its result, the panel says the result no longer fits, Apply goes off, and Measure again starts over. Close or Esc stops a running measurement.
- **The menus are tidier for a first-time user.** The same eight menus, but the rare commands sit in submenus at the bottom: File > Versions and More exports (the three first-hour exports stay in File), Track > Role and Bus, Text > Placeholders, Playback > Speed (fast, slow and shuttle in one), View > Options (mouse, inactive lanes, pauses, switches) and View > History. Help > Getting started lists the six things to do in the first hour. Nothing was removed, and every key still works.
- **A muted clip now shows a crossed-out speaker after its name.** It looked the same as a stretch Auto-Silence closed (outline only); now the padlock means Auto-Silence and the speaker means you muted it. The legend in the Auto-Silence panel says so.
- **M on a silenced stretch selects the clip it opens.** The stretch became its own clip but the old selection stayed on the left-over piece of the parent, so the next M muted the wrong thing. The new clip is selected, and M again mutes just it.
- **A project open in another window opens read-only, and a banner says who has it.** Inside the desktop app a second window on the same episode used to get a second writer, which could fork the history. Now it is read-only, and a band over the timeline says who holds it and since when ("Read-only: olli has this project open on Studio-Mac since 14.05 GMT+3"). Not seen on screen yet.
- **The menu bar flashes the menu that holds a command when you run it with a key.** Press a Cmd, Ctrl or Alt shortcut and the title of the menu where that command lives lights up for a quarter of a second (also the "…" menu when it sits there), so the keys teach you where things are, as macOS does. Plain keys (Space, J, K, L, the arrows) never flash; it is off when the animation setting is off. Not seen on screen yet.
- **Level blocks shows how far the measuring is.** The dialog has a progress bar and says what it is doing ("Reading track 2 of 3…", then "Finding the loud and the quiet blocks…") while it measures, instead of only "Measuring the speech blocks…". Behind it, analysis tasks that run in the worker can now report their progress to the editor (`analysis_progress.report`), so the other measuring dialogs can get the same. Not seen on screen yet.
- **Clips you play from the cart while recording are put on the timeline.** The record setup has "Clips you play go on": no track, a new track called Questions, or any track that is not being recorded onto (a warning appears when that track already has audio from the play cursor on). While the take records, every Clipboard entry you play (Alt+1 to 7, or a chip's Play) is also placed on that track at the take's place at that moment, as one undo step; this is the one edit that stays possible during a take. Not done: the clip is not trimmed when you stop it early, and its level is not matched to the voices yet. Not seen on screen yet, and not tried with a microphone.
- **A Material tab lists every recording of the project.** Cmd+6 (Ctrl+6) or View > Side panels > Show Material: one row per recording with its length, how much of it the edit plays (a bar: played, only muted or silenced, left out), whether it is a take, and two buttons: Copy to clipboard (the whole recording becomes a clipboard entry you can play, paste or place) and Place on timeline (copies it and pastes it at the play cursor as Paste does). Filters: All, On the timeline, Not on the timeline, Takes; a name search. Recordings never leave the project and nothing here changes one. Not seen on screen yet; takes in the recordings folder that were never put on the timeline are not listed yet.
- **The Clipboard has a cart: seven numbered slots.** Each Clipboard row has a number chip (a number 1 to 7, or a dash); click it to pick the number. Alt+1 to Alt+7 play the entry that holds that number, whatever else is going on, and Shift+Alt+1 to 7 give the picked entry that number (also in Playback > Cart). An empty slot says so. A number is held by one entry only. Seven, not nine, because Option+8 and Option+9 are the bracket keys on a Finnish Mac keyboard. Playing while recording does not put the clip on the timeline yet. Not seen on screen yet.
- **Transcription on Colab reports what it is doing.** Kuulas now asks the Colab tool for its structured events (`--events`): the toast says which step it is on (starting the machine, uploading, transcribing file 2 of 3, fetching the transcripts), a failure shows the tool's own one-line reason instead of its log, and a lost Colab session is recognised by the tool's own code. A tool that does not know the flag is run again without it, once, and remembered. Not tried against a real Colab, and the file name in the step text waits for the podcast side to send it.
- **The recording view stays out of your way.** Press Record and the record view steps aside; the timeline is in front with the take drawn on its tracks, and a track the take needs is made at that moment so it can be drawn. The view follows the take's end while you are watching it (and leaves it alone when you scroll away). Editing is paused while the take records, because a cut or move before it would put it in the wrong place; scrolling, zooming, selecting and adding markers still work, and the chip in the toolbar brings the record view and Stop back. Not seen on screen yet, and not tried with a real microphone.
- **Hold Cmd (Ctrl) while moving a clip to snap to the volume automation.** The clip's edges then also snap to the ends of a ducking ramp (a level change of 3 dB or more), to other clips' envelope level changes and to the edges of auto-silenced stretches; small marks along the top of the lanes show where, and they disappear when you let go. Without the key nothing changes. Not seen on screen yet, and not tried on a real ducked episode.
- **The Clipboard can be put in any order.** Drag an entry onto another row of This project (a line shows where it will land), or use Edit > Clipboard > move entry up / down for the picked one. The first entry is what Paste reads when none is picked; a new copy still goes first. Not while the list is filtered. Not seen on screen yet.
- **The stop notice says how much existing audio a take replaced.** When a take lands over audio already on its track, the notice adds "It replaced Olli 12.0 s. The earlier audio is kept in the project's files; Undo brings it back but removes this take too." The older recording files are never touched. Not seen on screen yet.
- **You see the tracks being recorded.** While a take records, each track it goes to is drawn on the timeline as the sound comes in (the loudest sample per pixel, with a red head where the take is now). A track that does not exist yet is drawn when the take stops; the view does not follow the head by itself. Not seen on screen yet, and not tried with a real microphone.
- **M on an auto-silenced stretch opens just that stretch.** Click a closed stretch (the play cursor lands in it) and press M: that stretch becomes a clip of its own with the mic open, and the rest of the parent clip is untouched. M again mutes just that clip, M once more unmutes it. One undo step. A cursor outside a closed stretch, several selected clips, or a muted clip behave as before. Not seen on screen yet.
- **Add markers while recording.** While a take records, Cmd+Enter (Ctrl+Enter) or the new Add marker button in the record view puts a marker where the take is now, not at the play cursor. The markers stay where they are when the take's clips land on the timeline. Not seen on screen yet.
- **Closing a toast keeps the next ones quiet.** After you press X on a message (a Colab transcription sends a new one every few seconds), new messages no longer pop the toast up again. A button on the status bar shows a dot and the latest text, so you can read the progress at a glance; click it to see the latest message as a toast again. Not seen on screen yet.
- **Focus mode keeps the other tracks readable.** The tracks outside the focus used to shrink to 16 px strips; they now share about 40 % of the room, between 16 and 64 px each, so their waveforms and clip edges can still be read. Not seen on screen yet.
- **Opening a project that is already open brings its window forward, whatever path you reach it by.** A symlink, a Dropbox link or another window's start page used to open it a second time (read-only since the lock fix); now the first window comes to the front. Not seen on screen yet.
- **The in/out selection is easier to see.** The band over the lanes is stronger (about a third more) and has a solid accent edge at both ends, also over a loud waveform. Not seen on screen yet.
- **A lost Colab session no longer fails the transcription.** The Colab tool keeps one session called 'whisper'; when it had died ("Session 'whisper' appears to be lost (404/401)") the job failed in the packaged app. Kuulas now tries once more with a fresh session ("The Colab session was lost. Starting a new one…"). The Colab CLI's update notices ("A new version of Colab CLI…", "To silence this check…") no longer show as progress or in error texts. Not tried against real Colab.
- **File > Export cut list (JSON).** Saves where your audio edit jumps: per speaker track every cut (where it lands on the timeline, how much of the recording was removed, and where on the recording clock), plus the places on the timeline where any track was cut, and the recordings' checksums. It is the data a video rough cut needs to hide jump cuts (the cover-shot rule itself belongs to autoraffkat). Nothing in the project or the recordings changes. Not seen on screen yet.
- **Edit > Clipboard > Copy to other window… (desktop app).** With two episodes open in two windows, it copies what is selected (or sends the picked clipboard entry) onto the other project's clipboard; that window says what arrived and you Paste there as usual (two actions instead of five). With more than two windows a small menu asks which. No key yet. The item sits in the menu greyed out until a second project window is open (checked when you come back to the window). Nothing is written to the other project except its clipboard; the recordings are checked by hash when you paste, as ever. Not seen on screen yet.
- **Menus and tooltips name Mac keys by their glyphs.** On a Mac, Backspace shows as ⌫ (the Mac's Delete key), Delete as ⌦, Enter as ↩, Tab as ⇥ and Esc as ⎋, like the system's own menus; Windows and Linux keep the words. Not seen on screen yet.
- **On a Mac, Ctrl+click is the context menu and never "add to selection".** Adding a clip or track to the selection and trimming one clip use Cmd+click on a Mac and Ctrl+click on Windows and Linux. Not seen on screen yet.
- **The side-panel tabs switch with Cmd+1 to Cmd+5 (Ctrl+1 to Ctrl+5 on Windows and Linux)**, like tabs in a browser; they were Alt+1 to Alt+5. Cmd+1 and Cmd+2 no longer also set the in and out marks: use I and O. Tab hints and tooltips show the new keys. Not seen on screen yet.
- **The padlock on a closed stretch is no longer hidden by the clip name.** It now sits just under the name strip (and the words row), so it shows on every closed stretch that has room; lanes too short for it show the outline alone. Not seen on screen yet.

- **The outline of an Auto-Silence-closed stretch is dimmer than a muted clip's.** Muted clips keep the full outline; stretches the gate closed are drawn at 60 %. Not seen on screen yet.
- **The Transcript shows only what is heard.** Words in muted clips, on muted or silent tracks, soft-cut with Backspace, or closed by Auto-Silence are no longer drawn, struck through or marked: the Transcript is for cutting what is there. The Cut and Delete keys count the words you see. A recording whose words are all muted is still known as transcribed, so it is not offered for transcription again. Searching removed material and putting it back come next.
- **Find shows words the edit does not play.** Under the find bar a line "Not in this edit: 3" opens a list of the matches that were cut, muted, gated (Auto-Silence) or are in a recording placed nowhere, each tagged with its reason (CUT, MUTED, GATED, UNUSED) and the words around it. Muted and gated hits have Show, which moves the playhead there. Text > "Find in removed material" (Shift+Cmd+F) opens the bar with the list open. Cut and unused hits also have Put back…, below.
- **Put back cut words, where they were cut.** In the find bar's "Not in this edit" list, Put back… on a cut or unused hit opens a preview: the sentence that comes back (kept inside what was removed, so nothing plays twice), where it goes, how far everything after it moves, and what each track gets. Enter puts it back as one undo step: a ripple insert at the seam on every track (or the selected tracks), the speakers stay in sync, a music bed is split and opened, and no recording is touched. When the original place is unclear (the pieces around it were moved or cut differently) nothing is guessed: it lists the possible places and offers Put back at the playhead.
- **The History panel's step sides are right after a Restore again.** A step that a Restore skipped is shown as rolled back, not as left behind, on the panel's page as well as the full list. An edit that has ever been restored takes the slower full computation for the panel, so a very long restored history may still feel a little slow on each edit.
- **The side-panel tabs show icons and the full shortcut when names do not fit.** On a narrow panel the inactive tabs become an icon plus "⌥1" (Alt+1 elsewhere), never a bare digit; the active tab keeps its name (at the narrowest width, name only). Every tab has a tooltip "Name (⌥1)". Not seen on screen yet.

## [v26.10.22.1] - 2026-10-22

- **Source (GPL):** Kuulas from this tag; the bundled speechmix, nhsx, silencelearn and automixer from github.com/ollisulopuisto/podcast at the main commit the dmg build checked out (8127aa7 when this release was made); pedalboard from github.com/spotify/pedalboard; ffmpeg from ffmpeg.org. Licences: docs/LICENSES.md.

- **Music report in the app.** File > "Music report..." opens a dialog with a preview table (title, artist, composer, publisher, programme start, duration, background/featured), a summary, warnings for pieces missing a title or artist, and Copy as table, Save CSV and Save HTML (the file name starts with the project name). Nothing in the edit: it says why (no music track, muted, no clips, silenced). No default key. Not seen on screen yet; saving uses the browser download, not a native save dialog.
- **Kuulas is released under the GPL (version 3 or later).** The repository now has a LICENSE file, the notice inside the app says so (the old "test build, do not redistribute" text is gone: it contradicted the GPL-3 library pedalboard that Kuulas loads), and the README says what Kuulas is in two sentences. docs/LICENSES.md lists the licences of everything the dmg ships.
- **The automixer is inside the app.** The dmg now ships the automixer, so a new user can automix without a podcast checkout, uv or ssh: with no command set, Kuulas runs its bundled automixer with the app's own Python (your own `command`, `cwd` and `remote` settings still win; from source it is still `uv run automixer` in the podcast folder). If it cannot start you get a specific message instead of a traceback, and if a chosen plug-in (VST3/AU such as dxRevive) is missing on this Mac it names the plug-in and the folders searched before anything is exported. Plug-ins are not bundled. The dmg grows by about 0.2 MB. Licences: docs/LICENSES.md (pedalboard is GPL-3; its notice now ships in the app as LICENSE.txt). Not verified: a real mix with the bundled automixer and the CI dmg build.
- **Every export honours the selection.** With In/Out marks or a painted range, exports cover that range on the tracks the range applies to (all tracks by default, the painted lanes, or the selected tracks); with selected clips and no marks, only the tracks holding them, from the first clip's start to the last one's end; with nothing selected, the whole mix. The running notice says so ("Exporting the selection only: tracks Anna, Ville, 12.00-18.30") and the file name carries the span and the tracks. The mix options and stems dialogs have "Only export the selection", ticked by default when there is a selection; the automixer dialog's box is "Only the selection". The Music report does the same ("Report of the selection only", a box "Only the selection"; tracks do not matter for it). Cmd+E has no toggle: clear the selection, or use the options dialog, to export everything. Not seen on screen yet.
- **The latest thing you chose is what Backspace and X act on.** When In/Out marks are set and you then select clips, Backspace, X, Alt+X, Cmd+X, close gap and copy act on the selected clips; the marks stay but are dimmed, and the status chip says so ("Backspace/X touch the 3 selected clips (the marks are dimmed)"). Setting or moving the marks makes the range the target again. Loop, play selection, paste and export still use the marks first. Not seen on screen yet.
- **History shows how far a Restore went.** Steps skipped by a Restore fold into one closed row "Rolled back N steps"; the restore row reads "Restored to: <step>", its target carries a "restore point" tag and a bracket in the margin joins them. Undone steps (Redo brings them back) sit above the current step as "Undone N"; steps left behind by an edit after undo fold into "Left behind N". Every kind has an icon and a word, not colour alone. Steps have readable names in your language ("Track settings: Olli · gain -3 dB" instead of set_track), and repeated steps on one thing show as one row ("x4"). Right/Left open and close groups, Enter restores, G goes to the restore point. The All steps | Saved versions switch is one control, and with Saved versions on a line says any step can be restored, with a link back to All steps; each saved version says where it stands (in the current state, undone, rolled back, left behind).
- **Editing keys work wherever you are, and say why when they cannot.** Cut, delete, split, mute, copy and the other editing keys work from any panel (not inside text fields or an open dialog); after an edit from a side panel the keyboard goes back to the timeline. A key with nothing to act on shows a one-line reason ("Nothing to cut: mark a range with I and O, or select clips") instead of a beep. Shift+X (delete on one track, closing its gap) no longer has a key: it is the one that breaks sync; it stays in the menu.
- **Esc steps back one thing at a time and never destroys work.** In order: an Auto-Silence preview (dropped, from any panel), the text field, the selected track headers, the selected clips with the range and in/out marks, focus mode; then the keyboard goes to the timeline. A selected word range in the transcript and typed text in the Clipboard filter go first and stop there. Esc no longer cancels a running export (use the notice's Cancel). Esc does not stop playback.
- **Cmd+S saves a version.** Cmd+S now saves a version named by the time ("Saved 14.32") that you see in History, with a Rename button in the message; if the current step is already saved it says "Already saved at 14.32" and adds nothing. It no longer makes a backup copy: the automatic backup every 10 minutes carries on, and File > "Back up now" makes one by hand. Shift+Cmd+S asks for a name first (a new name on an already saved step renames that version). File > "Open earlier version..." opens History with only the saved versions shown. Not seen on screen yet.
- **History shows your saved versions.** A version saved with "Save a named version" (Shift+Cmd+S) now appears in the History list: bookmark icon, bold name, a kind tag (Sent, Exported, ...) and the original step label under it. A toggle "All steps | Saved versions" at the top of the panel shows only the saved ones (remembered), and a text box filters by step or version name. Rename a version with "Rename saved version" (Go to menu, palette). 
- **The start page: remove entries from the recent list, and a pulse for the number keys.** Each row has "Remove from list" (hover, keyboard focus, or Delete on the focused row) with an Undo toast; it only edits the list and never touches the project folder or its files. A project whose folder was moved or deleted is shown dashed and muted ("Not found: moved or deleted") with "Locate..." (pick the new folder) and Remove; File > Open Recent has "Remove missing projects from the list". Cmd+1 to Cmd+9 now highlight the chosen row for a moment (180 ms, static outline with reduced motion) before opening it. The start page follows the system's reduced-motion setting, not the app's own "Animation off".
- **Alt+Space loops the selection.** It plays the marked range (or the selected clips) over and over from its start; press it again to stop. Shift+Space still plays the range once, as in Hindenburg. Also in the Playback menu.
- **Merge clips is Shift+Cmd+M** (the Hindenburg key; it was Alt+Cmd+J).
- **Export keys:** Cmd+E exports the mix, **Shift+Cmd+E exports the mix with the automixer**, Alt+Cmd+E exports the mix with options. "Export all tracks" and its options have no key any more.
- **A toggles range operations between all tracks and selected tracks** (it was E, which is now free).
- **Follow playhead is a state.** While playing, the view follows the playhead until you steer the view yourself (scroll, zoom, drag or click the overview, fit, view back/forward); then it stays where you put it and a small "Follow" chip (bottom right of the timeline) goes dim, with an arrow at the edge showing where the playhead is and its time. Follow comes back only when you stop or start playback, jump (any explicit go-to-time: Home, End, in/out, markers and the Markers panel, the go-to-time field, a click on a transcript word or search hit, Tab stops, drift and candidate rows), click the playhead itself, click the chip or arrow, or use View > "Show the playhead". Nothing re-engages it by itself. New in the View menu: "Follow playhead" and "Show the playhead" (Shift+P toggles Follow, Alt+P shows the playhead). Not seen on screen yet.
- **Side tabs stay on one row** with their Alt+1 to Alt+5 shortcuts visible on every tab; on a narrow panel the labels shrink (the shortcut stays in the tooltip).
- **The overview bar shows gaps where a track is silent** (no clip, muted clip or track, closed by Auto-Silence, or the Auto-Silence preview's would-close ranges): you see when somebody talks.

## [v26.10.20.38] - 2026-10-21

- **Automix keeps your music levels.** The Automix dialog has a "Music level" choice: **Keep my levels** (the automixer's `--keep-music-level`: music and effects get the same level change as the speech, so the balance you set by ear survives) or **Fit to speech** (the old bed rule, `--bed-under-speech-db`). Keep is the default when the automixer supports the flag and you have not set a bed level; the bed-level field is greyed while levels are kept. The two are never sent together. The toast and log say "Music: kept your level, +12.5 dB like the speech". The series stores the choice. Needs the podcast repo with PR 74 (git pull there); untried with the real automixer.
- **Auto-Silence can learn its Sensitivity from your own muting.** Mute the stretches you consider silence by hand, select clips (muted and unmuted ones), then Track > Auto > "Calculate Auto-Silence values from the selection": the Auto-Silence panel opens with Sensitivity filled in and says what was learned (or why not: too little muted material, nothing muted, missing audio, speech guard), and the live preview shows what it would close. Nothing is committed until Accept. Only Sensitivity is learned (clamped to 3-20 dB; several tracks use the smallest margin); Closeness and the times stay as they were. The maths is the shared `silencelearn` package of the podcast repo, shipped in the dmg. The values are taste values and untried on a real recording: check what it learns on a real episode.
- **The Clipboard has a series shelf.** The panel has four views: This project, Series, Shared (all projects) and Other projects. The Series view is the series music list: Paste here, Copy to this project, Take off shelf, Place on timeline; a project entry gets a Series toggle when the project belongs to a series. Moving an entry to a shelf copies it (the project's stays); a shelf refuses duplicates. Pasting a series entry first links any recording the episode lacks from where the series saw it (after a checksum check); no recording is copied, changed or deleted. New commands in Edit > Clipboard: "Clipboard: series shelf", "Add clipboard entry to series shelf" (no default keys). You can also drag an entry from any of the four views onto a track: the target track is tinted, each clip shows a dashed outline where it will land, the start snaps like moving a clip (Alt: no snapping, stop at a neighbour), and the drop is one paste in the panel's paste mode (Esc cancels). Dragging a single clip out of a multi-clip entry is not built. Not seen on screen yet.

## [v26.10.20.37] - 2026-10-21

- **Relinked clips keep their words.** After Locate / Relink media the new file inherits the old recording's transcript (trimmed if the new file is shorter), in the same undo step, and a missing recording nobody uses any more no longer shows up in File > Locate media. The Inspector shows "Mic kept open" for a clip that Auto-Silence never closes, with a button to let it be gated again.
- **Focus mode.** View > Focus mode: Shift+F makes the selected speaker's lanes tall and shrinks every other lane to a thin strip (greyed like inactive lanes); Alt+Shift+F also solos the speaker (and restores your solo set on leaving); Alt+F dims or hides the other speakers' words in the transcript. Up/Down move the focus by speaker, clicking another track moves it, Esc leaves it (after clearing the selection and marks). View only: saved lane heights and the project do not change. F stays Fit selection. Not seen on screen yet.
- **Silenced stretches are easier to see.** The body of a closed (Auto-Silence) stretch is clearly darker, and each stretch has its own thin dashed amber start and end lines (not draggable, unlike real clip borders). Clips in a group (Edit > Group) get one outline around the whole group.
- **Export defaults to FLAC.** The mix export (the dialog, Cmd+E and the remembered settings of a project that never chose) starts as FLAC 24-bit instead of WAV: lossless, about half the size, and every tool and Slack-style chat accepts it. A format you chose before is still remembered. Track stems (and the stems the automixer reads) stay WAV 24-bit.

## [v26.10.20.36] - 2026-10-21

- **Series: settings shared between episodes.** File > Series: "Save as series defaults..." stores the track layout (roles, speakers, buses, gains), the Auto-Silence options and the automixer's de-bleed values for a series; "New episode from series..." starts the next episode with them; "Apply series settings" pulls them into the open project as one undo step (it adds missing tracks, never removes a track or clip). Nothing is applied by itself. The status bar shows "Series: X - differs" when the episode departs from the series. Series music: "Add selected clips to series music", "Place series music on the timeline", "Put series music on the clipboard" (referenced by checksum, no recording is copied or changed). A series lives in ~/Library/Application Support/kuulas/series; each project keeps its own copy of the values, so it still opens when the series file is missing. Not seen on screen yet; apply writes the de-bleed values into the per-user automixer settings (all projects).

## [v26.10.20.35] - 2026-10-21

- **Silent, closed and missing clips look different.** A filled waveform sounds; an outline-only waveform is silent (muted, or closed by Auto-Silence). A padlock marks a stretch Auto-Silence closed, an open padlock after the name marks a clip that keeps the mic open. The hatching is gone, so clip borders are always visible and draggable inside a closed stretch. The Auto-Silence preview is a teal dashed outline. Lanes outside the current operation are greyed and lightly dimmed (View > Lanes outside the operation: dim, grey or both). A clip whose file is missing draws no waveform, a red outline and a warning sign.
- **Locate / Relink media.** Double-click a missing clip to locate its file; Clip > "Locate / Relink media..." is always in the clip menu, also for a file you edited elsewhere (different checksum). You confirm first with both lengths shown (a warning when they differ); neither file is changed or deleted; one undo step. The new file has no transcript yet.

## [v26.10.20.34] - 2026-10-21

- **Auto-Silence panel is easier to use.** Sensitivity and Closeness have a small number field and a full-width slider on its own line; buttons are normal height. The whole side panel can be hidden (View > Show side panel, or the x on its tab strip) so the timeline gets the width; it comes back by itself when you open Help, Auto-Silence options or a side tab. Remembered.

## [v26.10.20.33] - 2026-10-21

- **Automix only a part, and listen to the result in Kuulas.** The Automix dialog can run on the In/Out range only (result named "... preview mm.ss-mm.ss.wav"). After a render, Playback > "Listen to the rendered mix" (or the Edit | Rendered mix switch) plays the file on the timeline; a banner says which render and range, and you are put back on the edit automatically when you change the edit. Not matched in loudness. Untested with the real automixer on a range: check the render lines up with the timeline (an ad spot makes it longer).

## [v26.10.20.32] - 2026-10-21

- **Auto-Silence has a live preview.** Track > Auto > "Auto-Silence options..." opens a panel (docked over the sidebar, never covering the lanes) instead of a modal dialog: Sensitivity and Dominance have sliders, the other settings are under "More settings". The speech levels are measured once in the background (progress per track, Cancel), after that every change of a setting recalculates the silences in about 0.1 s and the timeline shows them as a preview (teal veil, hatch the other way, dashed edges, "preview" at the lane's edge; committed gates look as before). "Listen" plays the timeline with the previewed silences applied (same 30 ms edges as the real thing), "Accept" commits them as one undo step, Esc or Close discards everything. A per-track summary says how much would be silenced ("Aame: 12:34 of 45:10, 28 %, 41 stretches"). Clips that keep their mic open are left open in the preview too. An edit that touches the speech audio makes it measure again. Not seen in a window yet; known: the recalculation takes about 80-100 ms on a 45-minute, 4-mic project (the rest is inside speechmix).

## [v26.10.20.31] - 2026-10-21

- **The automix toast has a new layout.** Four fixed rows that do not jump in height: a title row (what is running, time left, percent), a full-width progress bar, a phase line ("Processing tracks - Step 3 of 4") and a track line ("Track 1 of 4 Olli - plug-in 3/9" with nine small stage marks, skipped stages shown as skipped). Cancel and Show log stay at the bottom right. It is built from structured progress the server now sends with the job, and falls back to the old single line when that is missing. Design notes and a mock: docs/design/TOAST.md and toast-mock.html. Not seen in the real window yet; narrow widths hide the stage marks.

## [v26.10.20.30] - 2026-10-21

- **A clip can opt out of Auto-Silence.** Select one clip or several and use Track > Auto > "Keep the mic open under the selected clips" (also in the right-click menu of a clip or a marked range): it is a clip property, so the mic stays open under the clip wherever you trim or move it (no more half-silenced clip when you drag the border) and a new Auto-Silence run does not close it. Used again on clips that are already open it lets them be silenced again. One undo step. A right-click on a hatched (closed) stretch also offers "Open this stretch" right there.

## [v26.10.20.29] - 2026-10-21

- **With the automixer's live events the toast stays on the event stream.** The plain text lines the tool still prints (block, loud, beds, ...) used to overwrite the toast message while the analysis ran ("2/4 [automixer] block Aame 43:05.4: +4.6 dB off ..."). Once events are flowing they go to the log only, and the toast shows the step, stage and percent from the events. Without events (an automixer that does not have `--events` yet) nothing changes.

## [v26.10.20.28] - 2026-10-21

- **The dmg build no longer depends on one ffmpeg server.** It failed for hours on 2026-10-21 because the host we download ffmpeg from answered 521. Now the build keeps a cached copy of the last good download (GitHub Actions cache) and, if there is none, a fallback copy kept as an asset of this repository's `ffmpeg-cache` release. Nothing changes in the app.

## [v26.10.20.27] - 2026-10-21

- **The automix toast shows the time left**, for example "... about 12 min left", once the bar is past 5 %. It is estimated from the automixer's own progress only (not the stems export, not the ssh upload or download) and appears after the first few progress updates. The estimate is rough: the automixer's bar moves in jumps.

## [v26.10.20.26] - 2026-10-21

- **Music ducking, second style: "Duck under speech".** The command Track > Auto > "Duck music under speech" now asks for a Style: "Fade in the gaps" (as before) or "Duck under speech" (continuous music that dips while someone speaks). The new style follows the automixer's sidechain law (speech loudness measured over 0.1 s, music lowered by the overshoot over a threshold, default -30 dB at ratio 8) with a short attack and release so it does not pump, measured in the background from the speech as heard on the timeline (gains and gates included, matched to the -19 LUFS speech target), and written as the same editable volume automation on every music track that ducks, in one undo step. Depth, Threshold, Attack and Release are fields in the dialog; the last style used is remembered. The automixer export and "Done in Kuulas" work as for the first style. Built by Codex and finished by Claude; never heard on real speech, so treat the defaults as a first guess and tell me how it sounds.

## [v26.10.20.25] - 2026-10-21

- **The last cut is remembered as a hidden marker.** After a cut, lift-cut or ripple delete, the splice point is remembered. If you then set only OUT (later in time) the IN marker is placed at the splice, and if you set only IN (earlier) the OUT is placed there, so the range extends from the cut you just made. A guessed mark is drawn dashed and lighter; setting both marks yourself overrides it, and Shift+Alt+I (clear marks) forgets it. Undo does not restore it.
- **Double-click on a clip's volume line adds a point** at that spot (on the line's current value); double-click on a point removes it. One undo step. Double-click elsewhere (rename, gate, placeholders) is unchanged. Not seen in a window yet.

## [v26.10.20.24] - 2026-10-21

- **Ready for the automixer's live events.** When the installed automixer supports `--events` (the podcast side is being built), Kuulas asks for it and reads the structured progress it prints: the toast then says which stage is working NOW ("track 2/4 Kari: plugin"), the bar follows the tool's own percentages, and the levels it reports (music bed, speaker balance, mastering) go into log.txt. Event lines never show up as text. With an automixer that does not have the flag nothing changes.
- **Recorder start waits up to 30 s** (it failed the dmg's own check at 10 s on a first start from a freshly mounted image).

## [v26.10.20.23] - 2026-10-21

- **A clipboard clip now mixes INTO the playback instead of taking it over.** While the timeline plays, Play on a clipboard entry adds it as an extra voice: the timeline keeps playing, the cursor does not move, and the entry ends by itself or with its chip's Stop (Space still stops everything). When the timeline is stopped it plays alone as before. It also starts much sooner: in a long project (over 2 minutes) the first preview no longer waits for the level of the whole project to be measured (it uses the default level once, and measures in the background for the next click).
- **The playback cursor no longer jumps back a few pixels.** Two causes: the cursor snapped back when a corrected position arrived slightly behind, and the engine dated the position reports with the time Python happened to run the audio callback. Now a correction slows the cursor briefly (never back, never frozen), and reports use the audio device's own time. Please check by ear and by eye.

## [v26.10.20.22] - 2026-10-21

- **The in/out band and bars are drawn only on the lanes the next cut will touch.** With all tracks in scope nothing changes (the band runs through every lane); after you pick one or more track headers (or press E) the band and the I/O lines appear only on those lanes, so it is clear at a glance what X, mute and delete will act on. The flags in the ruler stay.

## [v26.10.20.21] - 2026-10-21

- **Clicking a clip or a lane no longer narrows X, mute and delete to that one track.** The click makes the track current (inspector, split, paste) as before, but cut, copy, mute range and delete keep acting on all tracks; only a click on a track header (or Cmd+click) selects tracks for them, and Esc or E brings back all tracks. This had changed in v26.10.20.5.

## [v26.10.20.20] - 2026-10-21

- **How much may the automixer adjust the levels:** a new choice in the automix dialog, Speech group: Automatic (up to 6 dB, the default when you have not touched the levels), Fine-tune (up to 2.5 dB, the default when you have adjusted speech track gains or clip gains by hand) and Keep my levels (0 dB). It is sent as `--balance-speakers-max-db` only when it differs from the automixer's own value and only if the installed automixer supports the flag (the dialog says so otherwise). The choice belongs to the project and the run, it is never saved as a global default; log.txt says which value was used and why. Built by Codex; the automixer side is podcast PR #66.

## [v26.10.20.19] - 2026-10-21

- **Duck under speech (music).** Each music track has a "Duck under speech" choice (Inspector; on by default for music, never shown for speech tracks). Track > Auto > "Duck music under speech" measures when anyone speaks and writes the ducking as ordinary, editable volume automation on every music track that has it on (one undo step; drag the points afterwards). The automixer export carries that automation in the music stems and the automix dialog shows "Done in Kuulas" on the Music ducking option, so the export tells the automixer not to duck a second time (`--no-music-duck`); with no ducking written, the automixer keeps its own. Built by Codex; not tried in a window or on real speech. The design and the path to clip-level ducking later are in docs/design/DUCKING.md.

## [v26.10.20.18] - 2026-10-21

- **Run the automixer on another Mac.** Settings > Automixer > "Run on another Mac": the host (ssh alias or user@host), the automixer folder and a work folder on that Mac. Kuulas exports the stems, copies them over (rsync), runs the automixer there over ssh, shows its progress as usual (with upload and download steps) and copies the finished mix and flags file back; the remote work folder is removed afterwards, also when you cancel (Cancel stops the remote process too) or the connection drops. "Test connection" checks key login (never a password prompt), the folder, the automixer command, rsync, free disk space and which options that Mac's automixer supports. The plug-in list comes from that Mac. Needs an ssh key set up and the work folder name without spaces. Tried only against stand-ins, not against a real second Mac.
- **Show log while the automixer runs.** The running toast has a "Show log" button (next to Cancel) that opens an "Automixer log" window with everything the tool has printed so far, live (updates every second, scrolls down unless you scroll up, Copy, Esc closes); File > "Show automixer log..." opens it too, also after the run until the next one starts.
- **Tests that used the wrong clock fixed** (an export-name test failed between 00 and 03 Helsinki time).

## [v26.10.20.17] - 2026-10-21

- **Paste overwrites by default again.** Cmd+V pasted by inserting and pushed the later clips back; the change that made paste overwrite (Alt+Cmd+V inserts; with In/Out marked the paste is fitted to the range) had been left out of the release that announced it. Now in.
- **The automix progress says what is working now.** The automixer prints a stage name when the stage has finished, so "debleed" stayed on screen for minutes while the slow plug-in stage was running. The line now reads, for example, "track 1/4 Olli: debleed skipped (2/9), now plugin", and a stage that is switched off says "skipped".

## [v26.10.20.16] - 2026-10-21

- **The Loop button shows clearly when it is on:** accent fill and outline instead of the faint grey every toggle had.

## [v26.10.20.15] - 2026-10-21

- **The bus gain reaches the automixer too.** The stems now carry the gain of the track's bus as well as the track's own gain and the clip gains, so the balance you set by ear with tracks and buses together is what the automixer starts from. Pan, mute and ducking are still left out.

## [v26.10.20.14] - 2026-10-20

- **The automixer starts from the balance you set.** The track gain of every track (speech tracks as well as music) is now in the stems the automixer gets, together with the clip gains that were already there. The automixer does not equalise the speakers against each other, so a microphone you pulled down by hand in Kuulas stays pulled down in the automix. Bus gain, pan and ducking are still left out. (For an even starting point use Match loudness on the speech tracks first.)

## [v26.10.20.13] - 2026-10-20

- **Level blocks:** Track > Auto > "Level blocks..." measures the speech of each microphone the way the automixer does (stretches whose level is off, with the gain each would get), lists them per speaker with ticks, and applies them as clip gains in one undo step: the clips are split in the pauses between blocks and the gain is added to the pieces (20 ms fades at the new cuts), so you can see and change what the automixer would do. Loud spots stay as they are (optional markers). Running it again after applying changes nothing. The project remembers it, and the automix dialog then shows "Done in Kuulas" on the Block levelling option and the export sends `--no-block-level`. Not tried on real speech yet.
- **Cmd+drag (Ctrl on Windows/Linux) on a clip edge trims only that clip:** shortening leaves a gap and the neighbour is untouched; lengthening stops at the neighbour. The hint line and the ghost show it; Cmd+press on an edge no longer changes the selection.

## [v26.10.20.12] - 2026-10-20

- **Roles for buses.** A bus can be Speech or Music (right-click the bus header > Role, or Track > Bus); setting it gives every track on the bus that role in one undo step, and a track moved onto the bus follows it. A track's role is now a dropdown whose top choice is "Match bus role"; choosing Speech or Music is an override. A track that differs from its bus shows a "!" badge (click to match), and the bus shows "Music *" with a Reapply button when its tracks do not all match. Nothing changes in old projects; the export reads the tracks' roles as before.

## [v26.10.20.11] - 2026-10-20

- **The automix progress line says which step it is at**, for example "3/4 track 2/3 Kari: debleed (2/9)": 1 stems (Kuulas), 2 analysis, 3 the tracks (track i of n and the stage of nine), 4 mastering. The tool does not number its steps; Kuulas does, from the stage words it prints.

## [v26.10.20.10] - 2026-10-20

- **Music track gain now reaches the automixer.** The stems for the automixer used to leave out the track gain, so a contrast set by hand between an effects track and a music track (track gain) was lost in the export. The music tracks' gain is now in their stems; the automixer keeps the balance between music tracks, so the contrast stays. Speech tracks are unchanged (the automixer levels speech itself), and so are bus gain and ducking.

## [v26.10.20.9] - 2026-10-20

- **Progress shows when a stage is switched off.** The automixer reports "Olli: debleed" and "Olli: duck" for every track even when de-bleed or microphone ducking is switched off (nothing is done then). The progress line now says "(skipped: switched off)" for those, so it no longer looks like the stage ran.

## [v26.10.20.8] - 2026-10-20

- **Music level default corrected to +1 dB.** The automixer's real rule puts the loudest 3 seconds of the music 1 dB *above* the speech (not 1 dB below, as Kuulas assumed). The automix dialog now shows +1 as the default for "Music level against the speech (dB), negative is quieter" and sends `--bed-under-speech-db` only when you change it. The podcast repo has the flag in PR #64 (not merged yet): until it is merged and installed, the field has no effect, and the dialog says so.

## [v26.10.20.7] - 2026-10-20

- **Project folders stay small:** automatic backups are now compressed (about 10x smaller; a 112 MB history backs up as roughly 11 MB) and capped at 300 MB in total (the newest 2 and the newest of each of the last 3 days always stay; setting `backup_budget_mb` in the user settings file, 0 = no cap); old uncompressed backups are compressed when a project is opened for writing, each one checked before the plain copy is removed. A backup is skipped when nothing changed or the disk is nearly full. Statistics > Size shows media, history, backups, caches and recordings separately. New `kuulas restore-backup <folder> <backup>` restores from a backup (plain or compressed) after checking it, with a safety copy of the current file.
- **Set the music level by measurement:** Track > Auto > "Set music level...". Kuulas measures the speech (where someone speaks) and the loudest 3 seconds of the music, and sets the music tracks' level a chosen distance under the speech (default -10 dB; the numbers are shown before you apply, one undo step, repeatable). The music tracks keep their balance to each other. The project remembers that the music level was set, for a later export.
- **Automix dialog: music level under speech (dB)** in the Music group (default -1, the automixer's own rule). It is sent only when you change it and only when the installed automixer supports `--bed-under-speech-db`; otherwise the dialog says so and the music stays at its default level. The request to add the flag to the automixer is in docs/PODCAST-MAGIC.md.
- **Automix dialog knows what you did in Kuulas:** if you set the music level with "Set music level...", the Music field is pre-filled with that offset and marked "Done in Kuulas" (Reset puts back the automixer's own -1). A different saved value is kept and the dialog offers the Kuulas one; if the project has changed since, it offers to set the level again. It applies only when the installed automixer supports the flag, is not saved into your automix settings, and is noted in `log.txt`.

## [v26.10.20.6] - 2026-10-20

- **Automixer log kept:** every automix run now writes `<mix> log.txt` beside the mix (version, time, project, the full command and the automixer's output, so lines like "beds: loudest -xx LUFS, speech -yy -> beds +z dB" can be read afterwards); a failed run writes `... FAILED log.txt`. The finished notice has a "Show log" button and shows the beds/mastered lines.
- **A crashed analysis process no longer runs inside the app.** When the separate analysis process died (for instance killed by macOS for memory), the whole analysis was run in the app itself with no memory limit, which could bring back the memory blow-up. Now a crash is an error with back-off (exit code and signal named, a memory kill is flagged in the log); the in-app run is only used when the process cannot be started at all, one at a time, and refused when the app already uses more than 3 GB.

## [v26.10.20.5] - 2026-10-20

- **Memory stays small on long projects.** A 5-track, 90-minute project now needs about 1.1 GB in the editor and under 0.6 GB in the analysis process, however long it is (measured with synthetic projects; before, a long project could take 2-3 GB per process and swap the Mac to death). Playback, peaks, loudness, Auto-Silence and export read the audio in blocks and no longer keep a copy; analysis stops cleanly above a memory ceiling; canvases are size-capped. A mastered export is refused before it starts when it would need more than half the memory (about 55 minutes of stereo on a 24 GB Mac); the automixer itself still loads whole stems (its own code, see ROADMAP).
- **Paste overwrites by default** (Cmd+V): the pasted clip replaces what is under it and nothing downstream moves; Alt+Cmd+V inserts (moves later material along). With In and Out marked, the paste starts at In and is trimmed at Out.
- **Clipboard:** the Play button on a clip turns into a Stop button and a thin progress bar runs along the chip while it plays; the chip buttons are square; fixes a bug where a clip sometimes did not start playing.
- **Track highlight and selection follow the click** (clicking a clip or a track header selects that track; nothing is dimmed when nothing is selected).
- **Alt+1 to Alt+5** switch the side-panel tabs (Inspector, Candidates, Clipboard, Markers, History); View > Side panel.
- **Esc closes the topmost dialog and Enter accepts it** (Cmd+Enter from anywhere in it; in confirmations Enter is the safe choice). Esc/Enter chips show on the buttons.
- **Exports are named after the project**, not "Pääeditio": `05 diet woke litteroitu automixer 2026-10-20 15-33-43.wav`; the edit name is added only when it is not the main edit. Your own saved name templates are left as they are.
- **Automix dialog:** the option groups are clear collapsible cards (chevron, "N changed" badge, Expand all / Collapse all); the plug-in fields suggest installed plug-ins by fuzzy name (type "dxrev"; placeholder "Accentize dxRevive"); the block-levelling hint no longer says it is for Hindenburg only.
- **Dragging a group** outlines every member and the group as a whole.
- **One button style everywhere** (rulebook in docs/design/BUTTONS.md; a test stops new odd buttons) and **one form layout** (labels, fields, help text and footers line up in every dialog and panel; docs/design/FORMS.md).

## [v26.10.20.4] - 2026-10-20

- **Fixes the pile-up of background processes (v26.10.20.2):** the separate analysis processes were started for every loudness request, never finished under load and survived a restart, so dozens piled up and the Mac ran out of memory. Now at most one runs at a time, a newer request replaces the older one, each has a time limit, they exit by themselves when the app is gone, and the leftovers of the previous version are cleaned up when this one starts. The log lists child processes at start and exit.
- **The cursor no longer jumps back when you stop** (most noticeable when listening sped up), and while playing sped up with the pitch kept the cursor no longer runs 10-20 ms ahead of the sound.
- **Cmd+V pastes onto the selected track** (the topmost selected track, else the focused one; a multi-track copy keeps its layout below it). The paste target selector has a new default, "Selected track (else source)".
- **Music tracks are not transcribed:** recordings used only on music tracks are skipped by every transcribe command and the transcript panel says so ("Transcribe anyway" is there, local only). Nothing already transcribed is touched, and no music audio goes to Colab.

## [v26.10.20.3] - 2026-10-20

- **Your settings are remembered.** Preferences such as the fast-listening speed (1.75 stays 1.75), theme, drag mode and the panel choices were forgotten at every start; they are now saved in the config folder (`ui-prefs.json`). A few dialogs and the keymap overrides still use the old per-window storage.
- **Quick mute: press H** to mute a short stretch centred on the cursor (default 0.5 s, 0.25 s each side; Preferences > Quick mute length). Works while playing, honours the track scope, one undo step. Clip > Quick mute.
- **Automixer: every setting in the dialog.** Track > Auto > Automix now has a Processing section: Minimal, Speech, De-bleed and rider, Microphone ducking, Music, Plug-ins and per-track settings, with the tool's defaults shown. Only changed values are sent. "Other arguments" stays for anything else.
- **Start screen: Cmd+1 … Cmd+9 open the 1st … 9th recent project**, and the cards show the key.

## [v26.10.20.2] - 2026-10-20

- **Playback stutter fixes.** Background work no longer competes with playback: while audio plays, analysis, imports, waveform and loudness-curve work and exports pause ("Paused while playing" in the job list) and continue when you stop. Auto-Silence, automix and loudness analysis now run in a separate low-priority process, so they cannot take the audio thread's turn.
- **Cursor and sound stay together.** The cursor is now drawn smoothly from the sound's own timing instead of being polled, so it no longer trails. **Space stops the sound at once** (nothing already queued is heard) and the cursor rests where the sound stopped. Clicking far away while playing no longer plays the old place for a moment (about 0.1 s of silence instead).
- Smaller audio buffer (about 35 ms on the internal speakers); it grows by itself if the machine cannot keep up.
- **Help > Record a performance report…** samples the app for 10, 30 or 60 s and saves a text report (no project or file names) to ~/Library/Logs/Kuulas; Help > Log level sets how much the log says. Send the report if playback is slow.
- Block buttons (Undo, Redo, Restore and so on) are square.

## [v26.10.20.1] - 2026-10-20

- **Auto-Silence is adjustable:** Track > Auto > "Auto-Silence options…". Sensitivity (3 to 20 dB above the noise floor, default 12; lower is gentler), the dominance between mics, shortest pause to close, how long it stays open before and after speech, and a method choice: "Threshold over the noise" (as before) or "Compensated for bleed" (for mics that all hear everyone: it learns how much each mic normally leaks from the others from the stretches you muted by hand at the start, so it needs some hand mutes). **Preview** shows per track how many seconds would close; Apply is one undo step; the options are remembered per project and Alt+Mod+P uses them. The defaults give exactly the old result.
- **Track > Auto > "Open all gates on this track"** clears Auto-Silence's closed stretches on the focused track (one undo step).
- Auto-Silence stretches are drawn with the same hatching as muted clips; the "Mic closed" text is gone (hover explains it).
- The language is looked up lazily (no macOS subprocess at start-up). Hardening: take-plan files are size-limited, project paths from the app bridge are validated, a path starting with a hyphen cannot become a command option.
- Tools for the owner (not in the app): `scripts/spikes/wp85_sweep.py` finds the best Auto-Silence settings against your own hand mutes, `wp85_compare.py` compares Auto-Silence with colab-transcribe's mutes, `wp85_learn_silence.py` measures silencelearn; all read-only.
- Stems export writes `muted_frames` and `gate_frames` per track into `tracks.json` (optional, for the automixer work).

## [v26.10.19.29] - 2026-10-19

- **Fixes the app not starting (v26.10.19.28):** a crash at start-up ("cannot import name HOST") when the app is opened from Finder, caused by the new language setting being read too early. The build's self-test now runs without locale variables, like Finder does, so this is caught before a release.

## [v26.10.19.28] - 2026-10-19

- **Sync never moves anything; groups do.** Dragging a clip no longer drags its sync partners along: sync only lets you see drift and put a clip back (R). Clips move, trim, delete and mute together only when you have grouped them (Clip > Group clips, now Cmd+G; Shift+Cmd+G ungroups).
- **Which tracks a range edit touches:** the old "group editing" switch (E) is replaced by a visible scope. I/O marks and the keyboard act on ALL tracks; painting a range with the mouse in one lane acts on that lane only; clicking track headers (Cmd+click adds, Esc clears) limits cut, copy, lift-cut, close gap and delete to those tracks. **E** toggles "all tracks / selected tracks only" (also in the Edit menu and by clicking the chip in the status bar). Tracks that will not be touched are dimmed, and the status bar says what the next edit touches. It returns to "all tracks" when a project opens.
- **Dragging a clip's edge now overwrites its neighbours** instead of stopping at the first one (a short muted piece in between no longer blocks it); the preview shows what is trimmed or removed. Hold Alt to stop at the neighbour. Undo is one step; media files are never touched.
- **Slow listening:** hold Shift+J (backward) or Shift+L (forward) to play at half speed (0.25x, 0.5x or 0.75x, Playback > Slow listening) only while the key is down. The fast-listening speed nudges moved to `,` (slower) and Alt+`.` (faster).
- **Export:** the options dialog now lets you export the whole mix, the in/out range or chosen tracks, pick MP3 bitrate, WAV/FLAC depth and a loudness target, and says which tracks are silent because of mute or solo. Cmd+E repeats the last scope; File > Export in/out range.
- **Automixer dialog** redesigned: Mix, Output and a collapsed Advanced section, with defaults shown.
- **Timestamps:** type digits like Final Cut (110 is 1:10, 10000 is 1:00:00); **View > Language** switches Finnish and English.
- **Mac commands:** Cmd+N, Cmd+O, Cmd+W (Close project; refuses while recording), Cmd+, (Preferences), File > Open Recent, Cmd+M.
- **Clipboard preview** is never louder than the project (attenuation only, with a safety limiter; View > "Limit the clipboard preview to the project's level").
- **Security:** the local server refuses requests with a foreign Host or Origin header.
- The app icon's mark is larger. The menu opens submenus faster on hover (90 ms).

## [v26.10.19.27] - 2026-10-19

- **Start page:** each recent project is a card with when it was last opened, its tracks, length and size on disk, a marker if its folder is missing, arrow-key navigation, and Open/New in the app's button style.
- **Side panel buttons** are blocks like Play and Record (icon above the label), in one bar at the top of each panel; the duplicated panel title is gone.
- **The speed slider** no longer runs into the track headers.

## [v26.10.19.26] - 2026-10-19

- **The menu bar is shorter:** File, Edit, Clip, Track, Text, Playback, View, Help. Edit is back to the everyday things (undo, clipboard, select, find) with "Sync back" next to Undo; clip editing (split, merge, trim, group, mute, fade, level, sync) is in the new Clip menu; transcribing, the transcript and narration commands and cut candidates are in the new Text menu (Text > Transcribe). Rename is in Track and "Jump to typed time" in Playback. The recording settings are a submenu of Playback.
- **Colab progress is readable:** terminal colour codes no longer show up as boxes in the notice.
- A fresh recording can be given its place on the timeline later: the take file now has room for its position and track (groundwork for restoring a take).

## [v26.10.19.25] - 2026-10-19

- **Recording several channels at once:** the record view lists every input channel of the device; tick the ones you want, give each its own track (or a new one), and each gets its own meter. All takes land at the play cursor in one undo step. If one channel's file fails, the others keep recording and what the failed one had is kept.
- **The recorder no longer lingers:** it exits by itself after 60 s when nothing is recording and no editor is connected (never while a take or listening is on). A newer editor replaces an older idle recorder automatically; an older recorder that is recording is left alone and pre-roll waits.
- **Transcription works in the installed app:** it failed with "Litterointi keskeytyi" because the background worker could not start inside the app. The app's self-test now starts a worker, so a broken build is caught. Programs such as `uvx` and `colab` are found in the usual places even when the app is started from Finder.
- **Colab asks you to sign in to Google first:** Edit > Transcribe > "Sign in to Google for Colab…" opens the Google page, takes the code you copy back, and the transcription only starts after that.
- **Transcript panel:** one row per recording that has no transcript, each with "on this computer" and "on Colab" buttons (and "all N files"); the offer no longer covers the clock and start/end/length; the speaker's colour bar sits at the start of the words.
- **Menus:** the bar is now File, Edit, Track, Playback, View, Help. Playback holds Go to and Markers; Edit holds Transcribe, Transcript and narration, and Cut candidates. Submenus open when you hover over them.
- **Look:** the side panel's tab names are readable, buttons share one outlined style with icons, the inspector's fields line up.
- Take file names and the Recordings list (recover a take after undo) are designed but not built yet.

## [v26.10.19.24] - 2026-10-19

- **Recording pre-roll (default 60 s):** with the record view open, the recorder listens and keeps the last 60 seconds (setting: off / 10 / 30 / 60 / 120 s) in memory only; nothing is written until you press Record, and then the take starts that many seconds earlier. The take lands so the pre-roll ends where you pressed Record. The microphone is released by itself two minutes after the editor stops asking.
- **Transcription runs as a background job:** local and Colab transcriptions continue when you close the window; finished transcripts are added to the project automatically with a notice (one undo step per recording). Interrupted jobs are listed and can be restarted (Transcribe > Restart interrupted transcriptions).
- **Locate media… and Send a copy… (File menu):** point at a folder and missing media is relinked by content; "Send a copy" makes a copy of the project without media, with only the used parts (plus 2 s each side), or with everything.
- **Re-syncing asks first:** re-sync, re-sync all, re-sync to the end and send home show what will move before doing it (setting View > "Confirm before re-syncing"). The sync commands sit next to Undo in the Edit menu.
- **Cleaner window:** the duplicate macOS menus are gone (the app menu, Edit and View remain); the Undo, Redo, Import and Export buttons are gone from the top bar (Undo and Redo are at the top of the History panel); the transcript text lines up with the start of the tracks; the clock and start, end and length sit beside the transcript; a Record button sits next to Play. Note: Cmd+M (minimise) is gone with the Window menu.
- **Rule 17: recorded material is never lost** (written down in the plan; the Recordings list that makes every take recoverable is still to be built).

## [v26.10.19.23] - 2026-10-19

- **Next and previous drifting clip (Markers tab) are F7 and Shift+F7**, not N: N sits between B (split) and M
  (mute) and stays free. (Sync keys may be a little less handy than the everyday ones.)

## [v26.10.19.22] - 2026-10-19

- **Recording a single track (first version):** Transport > Record… opens the record view: choose the input and
  channel, the track to record onto (or a new one), watch the level meter (peak hold, clip light), the time and the
  disk time left, and press Record. **Stopping is two steps by default:** the first Space or click asks "Stop
  recording? Press again" (about 4 seconds; if you do nothing it keeps recording), the second stops. Settings
  (Transport > "Stopping a recording"): one click, or hold 2 seconds. Esc, hiding the view and closing the window do
  not stop a take (a red "Recording" chip brings the view back); the take is written by the separate recorder
  program, so quitting or crashing the editor does not stop it, and reopening the editor reconnects. When you stop,
  the take lands on the track as a clip at the play cursor in one undo step; the files are inside the project in
  `recordings/`. A take that was never imported (a crash) is offered when the project opens, never imported by
  itself. Playback is stopped while recording (use your interface's direct monitoring). A lost microphone, a low
  disk and a dead recorder all keep what was recorded and tell you. **Not tried with a real microphone yet and
  not in the .dmg app:** try it from Terminal with `uv run kuulas open <project>` and allow the microphone for
  Terminal; the checklist is in `docs/RECORDER.md` and `docs/TESTERS.md`. Not built: a level meter before you press
  Record, take markers, several channels (WP12b), pre-roll (WP12c).

## [v26.10.19.21] - 2026-10-19

- **Fixes from your testing:** a file dragged in from Finder now lands where you dropped it, not at the play cursor
  (desktop window); Alt+X (lift-cut) now really deletes the stretch, leaving the gap, instead of muting it (the
  copy still goes to the clipboard; Undo brings it back); Mod+Up and Mod+Down now move the selected clips to the
  track above or below (they did nothing before); pressing Alt+arrow very many times no longer makes the cursor
  jerk backwards (answers to older moves could arrive late and pull it back).
- **Light theme is a mid grey with more contrast:** panels and lanes are soft grey instead of white, text, borders,
  ruler, playhead, selection and waveforms read more clearly; the numbers are pinned by a test. Dark theme
  unchanged. Not seen in every state (transcript highlight, muted and clipping) yet.
- **No default key on the bracket keys or `/`** (your Finnish keyboard): previous and next view are only
  Alt+Cmd+Shift+arrows; next and previous cut candidate are Alt+Down and Alt+Up; next and previous drifting clip
  (Markers tab) are N and Shift+N; Help search is Shift+Cmd+K (Cmd+K is the palette); faster and slower playback
  are Shift+L and Shift+J (the comma stays for slower). Your own key overrides still work.
- **Colab transcription asks for the word-start correction** (`--align`, a setting, on by default); the result
  says whether it ran. The command now works from the podcast repo's main branch without naming a branch.

## [v26.10.19.20] - 2026-10-19

- **The recorder (part one of recording, no screen yet):** `kuulas-recorder` is a separate small program that
  records from a microphone and cannot be taken down by the editor. It writes each channel as a plain 24-bit WAV
  that is a valid, openable file at every moment (its size is updated every second and synced to the disk), keeps
  a journal of everything that happens, restarts itself after a crash into a new file and logs the gap, keeps
  recording if the editor closes, handles an unplugged microphone and a filling disk without losing what was
  recorded, and keeps the machine awake. Tested with a simulated microphone, including killing it mid-take; **not
  yet tried with a real microphone** (the Mac it was built on has none). The record button and view come next.
  Also small tested pieces for it: remaining recording time on the disk, names for takes, the 2-second hold to
  stop, level meters with peak hold.

## [v26.10.19.19] - 2026-10-19

- **Colab transcription follows the podcast session's answer** (the tool's plain-audio mode is still to be built on
  their side): Cancel now asks the tool to stop its Colab session first (SIGINT, up to 30 seconds), then terminates
  it, so a cancelled run does not leave a Colab machine running; the result's `timing` accepts any aligner version
  (`ctc-v1`, `ctc-v2`, …) and an optional count of words the aligner could not place; Google Drive is not mentioned
  or used (the mode sends the audio directly), so the "no Drive" setting is now an extra flag only older versions of
  the tool need and is off by default. The upload notice says the audio goes to a Google Colab machine directly.

## [v26.10.19.18] - 2026-10-19

- **Transcribe on Colab from kuulas (the kuulas side):** Track > Transcribe is now a submenu: "…on this computer",
  "…on Colab (audio is uploaded to Google)…" and the Colab settings. The Colab job runs `colab-transcribe` in a
  plain-audio mode (no `.nhsx`): progress and Cancel in the notice area, the words are stored with one undo step
  per recording and the recording is marked with how its times were made (`timing`: raw Whisper or corrected).
  The first Colab use per session shows a notice that the audio leaves the computer (you can tick "do not ask
  again"); Drive is skipped by default. **It cannot work yet:** the podcast side of that plain-audio mode
  (`--audio … --json … --progress`) does not exist; kuulas was built and tested against a fake tool, and the
  request is with the podcast session. Not seen on screen. Local transcription clears the `timing` marker.

## [v26.10.19.17] - 2026-10-19

- **The big clock is a control:** a single click copies the shown time to the system clipboard ("Copied 0:08,938");
  a double click (or Enter on the focused clock, or Spot on Cmd+J) turns it into a field: type a time and press
  Enter to jump, Esc to cancel. A number with a plus or minus is relative to where you are, like in Final Cut:
  `+100` jumps 100 seconds forward, `-30` thirty back, `+1:30` ninety forward; `ms` works as a suffix. The plus
  and minus you type do not zoom. The same typing sets the in and out marks in the Alku / Loppu / Pituus rows
  (a relative value moves the mark); in those rows a click still jumps to the mark and Alt+click copies the time.
  "Copy the time" is also in the Edit menu. **Spot (Cmd+J) had no handler before and now works.** Not seen on
  screen yet. Not done: the `f` (frames) suffix, since the project is audio at 48000 Hz.

## [v26.10.19.16] - 2026-10-19

- **Help search:** the first item of the Help menu is a text field (also on Cmd+/): type what you want to do and
  it lists the matching commands with where they are in the menus, their key and a line of explanation, then
  matching help topics. Up and Down choose, Enter runs the command, Alt+Enter opens its menu and highlights the
  item so you learn where it lives, Esc closes. It finds commands by their English or Finnish name, by what they
  do and by synonyms ("remove" finds Delete, "volume" finds Gain), and shows why a command is greyed out. The
  command palette now uses the same search. In the desktop window the native Help menu has "Search commands…",
  which opens the same search over the window. Seen working in a browser; not in the real desktop window yet.

## [v26.10.19.15] - 2026-10-19

- **The sync anchor is visible and choosable.** The anchor (the recording the others are kept in sync with) wears
  a small "anchor" tag on its clips' label strip, and hovering a drifting or free clip says "relative to
  <track>". **Shift+Y** (Sync menu: "Make this the sync anchor") makes the selected clip's recording the anchor.
  Nothing moves: what was in sync stays in sync, and Resync from then on goes relative to the new anchor.
  **Y** (Mark in sync, now wired; it needs two or more clips selected) makes the first selected clip the anchor.
- **"Sync selected clips to the anchor"** (R, Sync menu, palette) says what it did: "Synced 2 clips to Zoom. Time
  only, tracks unchanged.", "Nothing to do, already in sync", "Selection contains the anchor, nothing to move" or
  "The selection is not in a sync group". It already worked on a single clip that is not the anchor; the anchor
  itself is never moved. A resync that moves nothing makes no undo step.
- **Resync fixes time, never the track.** A clip dragged to another track remembers where it came from (the
  inspector and the hover say "moved from Anna"); **Shift+U** (Sync menu: "Put back on its original track") sends
  it back at the same time position.
- A clip moved onto the track of its own partner (or the anchor) is still a partner and no longer breaks group
  editing or drift (before, same-track clips were never partners).
- Not seen on screen yet. Sync points 1 and 2 (Alt+Mod+1/2) are still not wired.

## [v26.10.19.14] - 2026-10-19

- **Fixed: File > New project said "A project name cannot be empty" for any name.** On the Mac the save dialog
  hands back one path, which kuulas read as a list of letters (so the name came out empty). The same fault
  hit every other save dialog (exports). New project and Save as now take the name you typed.

## [v26.10.19.13] - 2026-10-19

- **The menus are reorganised** (your notes, WP74). **File:** New project…, Open project…, Import…; Save and
  Save a named version; Export mix (no automixer) on Cmd+E, Export mix (options)… on Shift+Cmd+E (the options
  window asks for the format and folder), Export mix (automixer)…, Export all tracks on Alt+Cmd+E and Export all
  tracks (options)…; Export transcripts as a submenu (subtitles, transcript text, chapters, regions, narration
  script); Statistics…. Holding Shift or Alt on an export item swaps it for its sibling. The per-format export
  commands left the menus (they are in the command palette). **Edit:** grouped into submenus (Delete and cut,
  Paste variants, Clipboard, Trim nudge and move, Split and merge, Groups, Select). **Track:** "Automix" is now
  "Duck the microphones (automation)" with an explanation, in a new Auto submenu with Auto-Silence. **View:**
  submenus Zoom and fit, Buses, Mouse and trackpad; no duplicate Loop. **Transport:** "Jump back and play" and a
  Fast playback submenu. **Go:** each Tab stop once; "Select the track above/below". **Markers:** Clear in and
  out points is Shift+Alt+I. **Cut candidates:** the menu shows Alt+Down/Up, which work on a Finnish keyboard
  (the bracket keys still work). Not seen on screen yet.
- **Auto-Silence, Duck the microphones and Transcribe the track now work from the menu and their keys** (they
  were greyed out and did nothing in the editor window before). Transcribe the track transcribes the focused
  track's recordings, or all speech tracks when none is focused.
- **Finnish terms:** väylä is a bus, ryhmä is a group, leike is a clip everywhere (about 60 strings changed);
  the table is in `docs/GLOSSARY.md` and a test keeps the old words out.

## [v26.10.19.12] - 2026-10-19

- **Tab also stops at markers and regions** (in every Tab scope: words, clip borders, sounds); a region gives its
  start and its end. Not tried on screen yet.
- Merged the other session's work (edit groups and free/drift sync states) with this session's packaging,
  statistics, scroll and automixer changes.

## [v26.10.19.11] - 2026-10-19

- **Edit groups and sync states on the screen (WP19a, R51):** Mod+G switches group editing off and on (the
  "Group editing off" chip stays visible while it is off). Select a clip and its partners, the clips of its sync
  group that play the same stretch of the recording, get a dashed outline: that is what a move will take along.
  Alt+Cmd (Alt+Ctrl) drag moves a clip alone; when it ends up out of sync, a message asks "Keep this clip free from
  sync?" with "Free it" (nothing changes unless you answer). **U** frees the selected clips from sync, or links them
  again: a free clip wears a grey unlinked icon and its offset ("+300 ms · free"), and is nobody's partner. A clip
  that drifted out of sync wears a red badge with its offset. The Markers tab lists the drifting clips, with the
  cause when you rest the pointer on one (read from the history, for example "since: cut, group editing off");
  `]` and `[` step through the list while that tab has the keyboard (the candidates keep `]` and `[` everywhere else),
  and "Resync all" and "Free all" are buttons there and in the Sync menu and the command palette. R, Alt+Mod+R and
  Shift+Alt+Mod+R (resync from the play cursor on) now work and say "Resynced 14 clips · skipped 2 free".
  Alt+Mod+X closes a gap on every track of the sync group. Not tried on screen yet: how the badges and the dashed
  outline look and fit in narrow clips, the message after an Alt+Cmd drag, and the Markers tab list.

## [v26.10.19.10] - 2026-10-19

- **Edits that move time keep the sync group together (engine; the screen comes next):** one rule now decides what
  an edit touches. Cutting and closing a gap, ripple delete, ripple trim, nudging and moving clips, and deleting
  words from the transcript take the whole sync group along (every track of it, or each clip's partners from the
  same stretch of the recording). Gain, pan, mute and Backspace-delete use exactly what you selected. With group
  editing off, only the focused track is edited. Music and other tracks outside the group are left alone when the
  edit started on a grouped track.
- **Free or drifting, never guessed:** a clip can be declared free from sync (pieces you split from it stay free; it
  is nobody's partner). A clip that sits away from where its sync group puts it, and was not declared free, is
  "drifting", with its offset and the edit that caused it read from the history. Nothing resyncs by itself. Resync
  from the playhead skips free clips and says "Resynced 14 clips · skipped 2 free". New: a list of drifting clips.
  The buttons, keys (Mod+G, U, `]` `[`) and badges follow in the next version; not tried on screen yet.

## [v26.10.19.9] - 2026-10-19

- **A downloadable Mac app for testers (unsigned):** `scripts/build_dmg.sh` builds `Kuulas <version>.dmg`
  (about 165 MB): drag Kuulas to Applications, open it once with right-click, Open (it is not signed), and
  double-click `.kuulas` projects. No Python, `uv`, repo or podcast checkout is needed: kuulas, its audio
  libraries and ffmpeg are inside. Each project opened from Finder gets its own window. Read `docs/TESTERS.md`
  for the testers' steps (including where the log is). Needs Apple silicon, `uv` and a network to build. Not
  opened in Finder yet: that is for you. Note: the local `Kuulas.app` launcher from `make_app.py` and this app
  both claim `.kuulas`, so remove the launcher (`lsregister -u`, see `docs/desktop.md`) before trying the dmg.
  ffmpeg in the bundle is a GPLv3 build (separate program; notice in the docs).

## [v26.10.19.8] - 2026-10-19

- **The automixer mix is now saved next to the project** (in the folder that holds the `.kuulas` folder, never
  inside it and not in the remembered export folder, which can sit in a synced folder), named
  "<edit> automixer <time>.wav". The dialog has a "Save the mix in" field if you want another folder.
- **A local `Kuulas.app` and the `.kuulas` file type (macOS, first step):** `uv run python scripts/make_app.py`
  builds `~/Applications/Kuulas.app` and registers the type, so Finder shows a project folder as one file with the
  kuulas icon and double-click, Open with… and dropping a project on the app or the Dock icon open it. A project
  that is already open on this computer is brought forward instead of opened twice (macOS asks once for
  permission to control System Events). Not signed; it needs the repo and `uv`. Undo with the `lsregister -u`
  line in `docs/desktop.md`. Not tried in Finder yet: that is for you.

## [v26.10.19.7] - 2026-10-19

- **Two-finger scroll zooms** (your choice): on a trackpad, moving two fingers up and down now zooms the
  timeline around the pointer, side to side scrolls time, and with the shift key held up and down scrolls the
  tracks. The notched mouse wheel is unchanged, and command or control plus scroll, pinch and alt plus scroll
  work as before. Switch back to plain scrolling in View > "Two-finger scroll: zooms / scrolls". Not tried on a
  real trackpad yet: check that the zoom direction feels right and that shift plus two fingers scrolls tracks
  (some browsers swap the axis).
- **Durations per clip, track and session** (statistics, inspector, status bar): the statistics now show the
  session duration and a table with one row per track: first clip start to last clip end, content (sum of clips),
  muted (muted clips plus the stretches Auto-Silence closed) and audible (the track without its mutes); a track
  that is muted or silenced by solo is flagged. Longest, shortest and average clip are listed. The inspector has
  a labelled Length field for the selected clip, and the status bar shows the total length of the selected
  clips. Lengths use the timeline's h:mm:ss.mmm. The old "audible speech" row is gone. Not seen on screen yet.
- Mix with the automixer: the help and dialog now say that track faders and pan are not applied, any recording
  format works and the project must be 48 kHz.

## [v26.10.19.6] - 2026-10-19

- **Session statistics:** File > "Statistics…" (also in the command palette) shows how big and how worked-on a
  session is: runtime (edit length, audible speech, recordings, time cut out), counts (tracks, clips, recordings
  used and unused, markers, regions, gaps, muted clips), who talked how much (when there is a transcript), and
  the work (number of edits by kind, saved versions, exports, first and last edit, active editing time where a
  break over 10 minutes does not count) and sizes. "Copy as text" and "Save as JSON" are in the dialog, and
  `kuulas stats <project> [--json]` prints the same from the command line without opening a window. Notes: undo
  is not recorded in the history, so there is no undo count; cuts made by transcript word-cutting before this
  version have no recorded length and are counted separately; mutes are not part of "time cut out". Not seen on
  screen yet. Also: building the timeline's word list is much faster on long sessions (about 1.5 s down to about
  0.1 s on a four-hour fixture).

## [v26.10.19.5] - 2026-10-19

- **Mix with the automixer: where the temporary stems go.** By default they go to your system's temporary folder
  (whatever the OS or `$TMPDIR` says), in a private folder of their own that is removed when the mix is done,
  cancelled or failed. The dialog's new "Temporary files folder" field lets you point them at another disk
  (for example an external drive) to save space on the main one; empty means the system folder.
- The automixer run now leaves nothing behind in the export folder (its empty "flags" file is removed; a flags
  file with notes in it is kept beside the mix) and no longer prints a confusing virtual-environment warning.
  First checked against the real automixer (a short test project, mix, progress bar and Cancel all worked).
## [v26.10.19.4] - 2026-10-19

- **Words inside the clips on the timeline** (as in Hindenburg): zoom in until a word is wide enough to read and
  each speech clip shows its words in a thin row under its label, each at its own place. The word under the
  play cursor is brighter and words you selected in the transcript are marked. Turn it off in View > "Words in
  clips" (the View menu now shows a check mark for switches like this). Not seen on screen yet: look at the row
  height, the contrast of the text over the clip and the zoom level where it appears (about 28 px per word).

## [v26.10.19.3] - 2026-10-19

- **Selecting words in the transcript also marks them on the timeline:** the selected words become the in and out
  marks, so you see where the edit would land in the waveform and can drag the marks to fine-tune it before you
  cut. (The transcript pop-up still acts on the words; to cut your fine-tuned range press X on the timeline.)
  Not tried on screen yet.
- Behind the scenes, small tested building blocks for coming features (series templates, chapter lists, filler
  words, safe file names, loudness number formats): nothing to see yet.

## [v26.10.19.2] - 2026-10-19

- **Levels before you export:** each track header shows the track's integrated loudness against the target
  (-19 LUFS for speech, -23 for music), the status bar has a live level meter (left and right, peak hold, marks at
  -18 and -6 dB) with a red clip light that stays on until you click it, and Track menu > "Reset track and bus
  gains to 0 dB" puts every fader back to unity in one undoable step. Not tried on real playback yet.
- **Clipboards belong to the project:** every project keeps its own clipboard history (`clipboard.json` inside the
  project, nothing is pruned any more; "Clear old entries" in the Edit menu keeps the newest 100). Mark an entry
  with the star to share it with all your projects. The Clipboard tab has three views: This project, Shared and
  Other projects (recent projects, or open any project folder, read-only), where you can paste an entry straight
  into the project you are editing. Entries you already had in the old per-user history move into the project they
  came from. The Pin button is gone. Not seen on screen yet.
- **The speech-mix track kind is gone** (separating a mixed-down file is outside kuulas). Tracks are speech or
  music; a project that had a speech-mix track opens it as speech. Alt+Mod+K now toggles speech and music.

## [v26.10.19.1] - 2026-10-19

- **Mix with the automixer from inside kuulas:** File > "Mix with the automixer…" (also in the command palette)
  writes the stems to a temporary folder, runs your automixer on them and saves the mix beside the project
  (`<edit> automixer <time>.wav`). Set the target loudness and an optional ad spot in the dialog; the command and
  its folder are remembered (default `uv run automixer` in `~/Documents/koodi/podcast`). It runs in the
  background with Cancel and a real progress bar (the automixer's `--progress` lines). The automixer gets the stems
  folder, so it reads them from disk and a full episode does not need to fit in memory. Only speech and music
  tracks are mixed: buses are left out of this job (normal exports are unchanged), music is
  exported as stereo, and a project that is not 48000 Hz is refused before anything runs. A missing program, a
  failed run or a run that writes no file each give a clear message. Not tried against the real automixer yet,
  only a fake one.

## [v26.10.18.70] - 2026-10-18

- **The clip you drag shows its waveform:** the ghost of a moved clip now draws its real waveform (with the clip and
  track gain, in the colour of the track it would land on), so waveforms can be lined up by eye. Not seen on
  screen yet; the smart guide lines come later.

## [v26.10.18.69] - 2026-10-18

- **Dragging paints a range by default** (your preference, switchable in View > "Mouse: dragging paints a range /
  moves clips"): drag across a clip or an empty lane to mark a region, then Backspace to mute it or X to delete
  it. Move a clip by dragging its **label strip** (the title row at its top) or with **Cmd** held. The old way
  (drag moves the clip, Shift or Alt paint) is one switch away.
- **A selection of several clips is dragged as it is:** after "Select forward" a plain drag on any selected clip
  moves them all; a single clip you just clicked still paints a range.
- **Moving clips snaps:** the edges of the moved clips snap to other clips' edges, the playhead and the in/out marks
  (within 8 pixels, shown by a thin line); hold **Shift** to move finely (a tenth of the travel) and **Alt** to
  turn snapping off.
- **Giving material back on all tracks at once:** Shift+drag a clip's end edge outwards (with group editing on):
  the clips on the other tracks that end at the same splice grow by the same amount, as far as their recordings
  reach, and everything after moves along, so no track is left with a gap.
- **B (split) shows at once** instead of after the server's answer.
- **Cmd+Backspace** removes the selected clips and leaves every other clip where it is.
- **The right-click menu** lists only what is possible, scrolls if it is still too tall, and shows hints in the
  status bar. **Drag the speed display** (with fast listening on) to change the speed.

## [v26.10.18.68] - 2026-10-18

- **The transport has its own corner:** Play, Silmukka (loop), the timecode and the fast-listening speed now sit
  above the track headers instead of in the menu row, so all 11 menus fit at 1280 px and wider. Next to
  them, **Alku, Loppu and Pituus** (in, out and length of the marked range) are stacked: click one to jump
  there (Pituus zooms to the range), double-click to type an exact time. The length is also drawn on the
  range band in the ruler, and the status bar no longer repeats the marks. Narrow windows (under about 1400 px)
  use a more compact corner. Checked in a browser by the builder, not yet on your screen.
- **No overlapping clips:** moving or nudging a clip onto others now overwrites them: the clips under it are
  trimmed, split around it, or removed when covered; one undo step; nothing is lost (a trimmed clip still
  points at its whole source). Old projects keep their overlaps.

## [v26.10.18.67] - 2026-10-18

- **Hindenburg clipboards come in with the import:** each clip in a session's clipboards (1 to 4) becomes a
  pinned entry in the Clipboard tab, named "Hindenburg clipboard 1: start", with its regions, gains, fades
  and mutes. Not tried on your session yet; importing the same session twice adds the entries twice.
  Hindenburg's markers (including its in and out points) are still not imported.

## [v26.10.18.66] - 2026-10-18

- **The waveform shows the gain:** its height follows the clip gain, the track gain and the clip's gain
  envelope (at 0 dB it looks exactly as before). Parts that would clip after the gains (over -0.1 dBFS) are
  drawn **red**; hovering a clipped clip says how far over it is ("Clipping: +2.1 dB over full scale"), and its
  gain line turns red too. Bus gain is not counted yet. Not yet seen by eye.

## [v26.10.18.65] - 2026-10-18

- **Where you left off:** the play cursor, in/out marks and view are saved in a small `resume.json` inside the
  project folder, so they come with the project through Dropbox to the other Mac; saved at least every 5 s
  while playing, on Cmd+S and when the window closes. On opening you get "Back where you left off: ...", a
  "Left off" flag on the ruler, a pinned row in the Markers panel and Go > "Go to where I left off".
- **Bug reports name the build:** the status bar shows `v26.10.18.65+<commit>` and `--debug` prints it first.
- **X now deletes and closes the gap without touching the clipboard** (Shift+X: this track only); **Cmd+X cuts
  to the clipboard.** X works from any panel except text fields and the transcript. After a cut the in/out
  marks and selection are cleared, and Undo brings the marks back. Esc clears the marks too.
- **Cmd+Alt+click** selects the clip and every clip after it on all tracks.
- **Keys:** 1 and 2 jump to the in and out marks (Cmd+1 and Cmd+2 set them); Shift+Space plays the marked range;
  Cmd+Shift+Space rehearses the edit (3 s before the in point, jump over the range, play on).
- **Clearer timeline:** the active track's lane is tinted with a bar at its left edge and the other lanes
  are veiled; Tab jumps to the next clip border on any track by default; adjusting a clip no longer drags the
  play cursor along; with overlapping clips the shorter one is clicked and drawn on top.
- Not yet seen by eye: everything above that draws on the timeline or in the window.

## [v26.10.18.64] - 2026-10-18

- **Fast listening:** the `.` key toggles pitch-kept sped-up playback; `,` and `/` slow it down and speed it
  up in 0.05× steps between 1.0× and 2.0× (hold to repeat), Alt+0 goes back to normal; a slider and a chip show
  the exact speed (for example 1.35×). Stepless, can be changed while playing, remembered. Not yet heard by
  ear.
- **Scrubbing back with J at speed no longer runs the audio dry:** the engine re-mixed the tracks up to 489
  times in one block; it now mixes once (worst block 56 ms down to 0.9 ms in the benchmark).
- **Cursor keys:** Left/Right now move the cursor a few pixels at the current zoom, like Hindenburg, for fine
  work on cut points; Shift+Left/Right is 1 s, Alt+Left/Right 10 ms. (The old 5 s step is gone.)
- **Tab:** steps through the stops of a scope you cycle with Alt+Tab on the Mac (Shift+T elsewhere): words,
  clip borders, or sounds; the status bar shows "Tab: words" and so on. Tab now also works after clicking a
  track header, and the word stops are always current.
- **Right-click menus** on the timeline: on a clip (cut, copy, paste forms, split, group, merge, select
  forward, trim, level), on a marked range, on empty lane space and on the ruler. Every command is also in the
  menu bar (new Transport, Go, Transcript and Cut candidates menus).
- **Cuts:** after X, Alt+X or closing a gap, the in/out marks, the range and the selection are cleared from
  the screen. Palette: a word from a command's description finds it. "Select forward from selected clips, all
  tracks" no longer picks up long clips that merely overlap.
- Not yet tried by eye: the right-click menus, the status-bar scope indicator, the speed slider.

## [v26.10.18.63] - 2026-10-18

- **Projects can live in Dropbox (and Syncthing, iCloud):** each open copy of kuulas now writes its own small
  lock file in `locks/` instead of everyone rewriting one `lock.json`, so a synced folder no longer grows
  "conflicted copy" files. Opening checks all of them: a fresh lock from another computer refuses the open
  and names it; a lock older than 5 minutes (sync delay allowed) is ignored. The database side files are
  flushed when nothing is being written and on close, and marked "ignored" for Dropbox on macOS.
  **Every computer must run this version:** an older kuulas does not see the new locks. Not tried against a
  real Dropbox yet; keep one computer on a project at a time.
- Fixed: after a jump with the player stopped (Home, End, Tab, markers) the timeline now scrolls to show the
  playhead.
- Finnish: narration is now "juonto" (juontopaikka, juontokäsikirjoitus).

## [v26.10.18.62] - 2026-10-18

- **Track kind tags:** Alt+Cmd+K cycles the focused track between speech, speech mix (several people in one
  file) and music, one undo step. The kind icon in the track header is now a button that does the same, and
  the track inspector has a **Speaker** field: tracks with the same speaker count as one microphone in the
  analysis (blank means the track name). Not yet seen in the real app.
- **Clipboard, finished:** new paste forms "paste on the entry's own tracks" and "overwrite on the current
  track" (Edit menu and palette); at most 50 unpinned entries are kept, pinned ones never drop; **Play** on a
  clipboard entry previews it without touching the project; a copy in one window shows up in the other
  windows; an entry can be pasted into another project (recordings are linked in place when the original file
  is still there and unchanged). Entries get names like "3 clips from Olli, 00:12:04", and the Clipboard tab
  has a filter box and shows source project, tracks and length. Not yet seen in the real app. Still open:
  pasting when the original file is gone (needs excerpts), preview without gate or automation.

## [v26.10.18.61] - 2026-10-18

- **Group, ungroup and merge clips**, all undoable in one step. Group (Alt+Cmd+G) ties the selected clips so
  clicking, dragging, cutting or muting one takes the whole group; Ungroup is Shift+Alt+Cmd+G. Merge
  (Alt+Cmd+J) joins touching clips of the same source and gain into one clip. Edit menu and palette have all
  three. Grouped clips show a small joined-rings badge. Not yet seen in the real app: the badge and
  dragging a grouped clip.

## [v26.10.18.60] - 2026-10-18

- **Mono speech tracks:** a track has a **Mono** switch (inspector checkbox, and a "mono" or "stereo" tag on
  speech tracks). A mono track is mixed to one channel everywhere, (L+R)/2, so a centred voice keeps its
  level, and its exported stem is a one-channel file. Speech from a mono file is mono by default.
- **A stereo speech file comes in as stereo speech** and, after the import, a notice asks "Turn into mono /
  Keep stereo" (naming the tracks); a setting in the import options remembers the answer (always ask,
  always mono, always stereo). **Not for projects imported from Hindenburg:** tick Mono on a track's
  inspector yourself (for example Olli).

## [v26.10.18.59] - 2026-10-18

- **Exports ask where to save** (in the desktop window): "Export all tracks", "Export all tracks as…" and
  "Export mix" open a folder chooser first, starting at the folder you used last time for this project
  (else `<project> exports` next to it). The files still go into a new sub-folder named with the edit and
  the time, so nothing is overwritten. Cancel in the chooser cancels the export. **File > Export all tracks
  to the last folder** (and Alt+click on the "Vie" button) exports without asking.

## [v26.10.18.58] - 2026-10-18

- **Fixed: exported WAV files now open in macOS Quick Look and CoreAudio.** The RIFF size field in the header
  was 0 (and the right number was written as four stray bytes at the end); audio editors tolerated it,
  Apple's player did not. Re-export any WAVs made with earlier versions. Applies to every WAV export
  (stems and mix), and an odd-length data chunk is now padded as the format requires.

## [v26.10.18.57] - 2026-10-18

- **Esc clears the clip selection** (and the lanes of a dragged range) but keeps the in and out marks.
  Inside a text field Esc still leaves the field first; with nothing selected it still returns focus to
  the timeline.

## [v26.10.18.56] - 2026-10-18

- **More export formats through ffmpeg:** WAV (still the default, 24-bit), FLAC, AIFF, MP3, AAC in an M4A
  file (on a Mac with AudioToolbox the hardware-accelerated `aac_at` encoder), Opus and Ogg Vorbis; the list
  shows only what your ffmpeg can encode (`kuulas export-tracks --list-formats`; on this Mac Ogg Vorbis is
  missing because ffmpeg has no libvorbis). File > **Export mix** (one file, new) and File > **Export all
  tracks as…** list the formats; the one-button "Export all tracks" stays WAV. Terminal: `kuulas export-mix
  <project> [--format ID] [--kbps N]`. The mix is one file `<project> exports/<edit> <stamp> v<n>.<ext>`.

## [v26.10.18.55] - 2026-10-18

- **Alt while dragging a range** turns it into the clips it touches: they are highlighted live, and on
  release they become the selection and the in/out marks are set to their span. Without Alt the exact
  range is kept. Alt+drag over a clip starts a range (a plain drag over a clip moves it, Shift+drag
  marks a range). A hint at the top of the band says which key does what. Not seen in a real window yet.

## [v26.10.18.54] - 2026-10-18

- **Dragging a clip moves it, as in Hindenburg:** a plain drag anywhere on a clip's body moves it (it was only
  the top strip). To mark a range over a clip, hold **Shift** and drag; a plain drag on empty lane space
  still marks a range. Edges still trim, the gain line and fade corners still work.

## [v26.10.18.53] - 2026-10-18

- **Selection commands** (Edit > Select, and the palette): select the range on all tracks, the clips a range
  touches, set the range from the selected clips, select everything forward from the playhead or range
  end, add every later clip on each track of the selected clips (also across all tracks), invert
  (Shift+Cmd+A) and select none (Cmd+D). **Cmd+click** toggles one clip in the selection. The status bar
  shows the selection too: "3 clips · 4:12-9:50 · 5:38". Most of the new commands have no key yet:
  use the menu, or map your own in the keymap.

## [v26.10.18.52] - 2026-10-18

- `docs/KEYS.md`: a list of every keyboard shortcut (Mac and Windows/Linux), generated from the keymap
  (`node scripts/make_keys_doc.mjs`; a test fails when it is out of date).
- Building blocks for later, not visible yet: zoom to a range dragged on the ruler, and hover tips.

## [v26.10.18.51] - 2026-10-18

- **Move a clip by dragging its label strip** (the top 20 px of the clip): in time and onto other tracks,
  with a dashed ghost; Esc cancels; one undo step; sync partners follow in time under group editing.
  A drag over the waveform still marks a range.
- **Drag the gain line** of a clip up or down (live, +12 to -30 dB) and **drag the top corners** for fade in and
  out; Esc restores. Handles show on a selected or hovered clip.
- **Fixed:** dragging a clip's edge to trim never started (the drag distance was computed wrongly).
  Edge trims (roll, and ripple with Shift) work now.

## [v26.10.18.50] - 2026-10-18

- **Tab and Shift+Tab** move the playhead to the next / previous word start or transient (in the timeline
  and the transcript; Tab keeps its normal focus move in side panels and text fields). **Shift+T**
  cycles word / transient / both; the choice is remembered. Transients are detected from the focused
  track (or all audible tracks) in the background. Not tried on a real window yet.

## [v26.10.18.49] - 2026-10-18

- Plan change (owner): mouse editing (WP6) and Tab to the next transient or word (WP19i) are part of the first
  playable build now. Building block for the status list settings (rename, add, remove, reorder statuses):
  logic only, not visible yet.

## [v26.10.18.48] - 2026-10-18

- **Export all tracks with one button:** the "Vie" button in the toolbar, File > Export all tracks, or
  Shift+Alt+Cmd+E writes one 24-bit WAV per track (edits, clip gain, fades and mutes applied; no
  track effects, buses or master), all the same length and starting at the same moment, plus a
  `tracks.json` list, into a new folder `<project> exports/<edit> <date time> v<n>/` next to the
  project. It runs in the background with progress and a Cancel button, and "Show in Finder" in the
  desktop window. A muted track, or a track on a muted bus, comes out silent (the notice says
  which). From the terminal: `kuulas export-tracks <project.kuulas> [--out F] [--format wav|flac]
  [--bit-depth 16|24|32]`. For the automixer: music tracks get " MUSIC" in the file name, because
  the automixer reads the role from the name.
- Fixed: a track export ignored a muted bus (the stem came out at full level).
- An end-to-end test now drives the whole editing loop on a synthetic three-speaker episode (import,
  X, Backspace, trims, undo, save and reopen, export).
- Read-only projects cannot export (the export also writes a record into the project).

## [v26.10.18.47] - 2026-10-18

- **Collapse a bus:** a chevron at the left of the bus header, a double-click on the header, or
  Alt+Cmd+Left / Right; View > "Collapse all buses" / "Expand all buses". A collapsed bus shows one thin
  strip per member track (in the speaker's colour). Remembered per project. Only buses with two or
  more tracks collapse.
- **Right-click menus** on a bus header (collapse or expand, rename, mute bus, ungroup) and on a track
  header (rename, mute, solo, group into a new bus, remove from bus).
- Shift+click on a collapsed bus adds the member clips at the clicked time to the selection.

## [v26.10.18.46] - 2026-10-18

- **Drag a clip's edge to trim it** (6 px at each end of a clip): by default the cut moves and nothing
  else does: if a clip touches that edge (a muted one after an active one) it gets shorter while the
  dragged clip gets longer; with nothing next to it the edge just trims or extends. **Shift** while
  dragging makes it a ripple: only that clip changes length and everything after it, on all tracks,
  shifts by the same amount (shrinking removes that stretch on the other tracks too, as X does).
  A ghost shows the new edge, Esc cancels. Not looked at in a real window yet.
- **Playback stalls:** the audio no longer reads files inside the audio callback (a read-ahead cache is
  filled in the background and warmed before play starts), and the audio thread gets Python's
  lock back faster. `--debug` shows `miss` counts and a `gil?` hint. Please run with `--debug` again.
- Building block for nested buses: the bus tree rules (depth, badges A / A1 / A1a, mute and gain
  cascade). Not visible yet.

## [v26.10.18.45] - 2026-10-18

- **Finnish keyboard:** candidates step with **Alt+Down / Alt+Up** (the brackets stay), and the
  previous/next view with **Alt+Cmd+Shift+Left / Right** (Alt+[ and Alt+] stay).
- **Menu bar:** menus that do not fit the window move into a "…" menu instead of hiding behind the
  Play button.
- **Fit tracks to window** fits every track (it resets lanes you had sized by hand); a lane is only
  resized after a real drag of the header's edge; a scroll thumb shows when the lanes do not fit.
- **Transcript:** muting then unmuting a track no longer leaves its words struck through (the server
  merged the two clicks into one step, so the head did not change and the transcript never reloaded).

## [v26.10.18.44] - 2026-10-18

- **Cmd+S works:** it makes a backup copy at once and says so; Shift+Cmd+S makes a named
  checkpoint ("Saved 11.45"; checkpoints are stored but not listed in the History panel yet).
  Every edit was already saved as you made it.
- **Speech waveforms are drawn in dB again by role:** speech and speech mix are dB-shaped (big),
  music is linear (small), by default; before, every track was drawn linear, so changing a role
  only changed the colour.
- **New bus:** every "+ New bus…" path ends with the new bus selected and its name field ready.
  The role choice reads "Speech mix (several people in one file)" so it is not mistaken for a bus.

## [v26.10.18.43] - 2026-10-18

- **Lift-cut (Alt+X):** copies the selection or in/out range to the clipboard and removes it in place,
  keeping the gap (restorable), as one undo step. **Close gap on all tracks** is now **Alt+Mod+X**
  (it ripple-closes the selected range on every track without touching the clipboard).

## [v26.10.18.42] - 2026-10-18

- **Drag to mark a range:** drag across a lane's waveform or empty space to set the in and out marks;
  X, Backspace, Mod+C, play selection and the loop then act on that range. Esc cancels.
- **In and out marks:** a lone mark is drawn now (before, nothing appeared until both were set), and the
  marks can no longer reverse: an out mark before the in mark replaces the in mark, and an in
  mark after the out mark replaces the out mark.

## [v26.10.18.41] - 2026-10-18

- **Track heights:** View > "Fit tracks to window" sizes all lanes to fill the window; "Auto-fit
  tracks" keeps them fitted when the window or the tracks change (the −/+ buttons switch it off).
  Drag the bottom edge of a track header to size one lane (double-click resets it). All remembered
  per project. Not looked at on a real window yet.

## [v26.10.18.40] - 2026-10-18

- **Loop playback:** a Loop button next to Play and View > Loop (key **Mod+U**; Mod+L is Automix)
  loops the in/out marks, else the selected clips. It plays gap-free with the same short crossfade
  as a skip and follows soft cuts; the loop is shaded on the ruler and remembered per project.
  Not heard on a real device yet: please try it with a short in/out range.

## [v26.10.18.39] - 2026-10-18

- Transcript: between two paragraphs of the same speaker that were split by a pause you now see the
  length of the silence ("6,4 s"); clicking it sets the in and out marks to that silence. View menu
  > "Break paragraphs at pauses over": 1.5 s, 3 s (the new default), 6 s or never. Before, every
  pause over 1.5 s started a new paragraph.
- Building blocks for status tracking (ready for review, reviewed, needs fixes): the status list and
  history model, and the chip colours. Not visible in the app yet.

## [v26.10.18.38] - 2026-10-18

- Fixed the "project is open on this machine, read only" trap: a lock left by a kuulas window
  that crashed or was killed on the same computer is taken over at once, instead of after two
  minutes. A lock held by a kuulas that is really still running still opens read-only.
- `kuulas open <project> --debug` (also `kuulas desktop --debug`) prints playback diagnostics once a
  second to the terminal: how long each audio block took, how much of that was reading files or
  mixing, late and failed blocks, the device and the slowest files. For finding out why
  "playback cannot keep up".

## [v26.10.18.37] - 2026-10-18

- A track's role (speech, speech-mix, music) can be changed in the inspector. The import no
  longer calls a stereo file music: only a name with "music", "musiikki" or "jingle" does. (A stereo
  speech recording had come in as music and drawn a small linear waveform.)
- The status bar shows In, Out and Length when in/out marks are set or something is selected.
- The sidebar's five tabs shrink to fit the narrow sidebar instead of running off the edge.

## [v26.10.18.36] - 2026-10-18

- Bus headers have two lines now: name and M on top, the bus level and pan below, always visible
  and large enough to use (they were squeezed onto one line and shown only on hover).
- The transcript shows the words of a silent track as deleted text: a muted track, a track on
  a muted bus, and every track while another one is soloed.

## [v26.10.18.35] - 2026-10-18

- The bus choice in each track's header has "+ New bus…" too: it makes a bus and puts the track
  on it in one step (it was only in the inspector before).

## [v26.10.18.34] - 2026-10-18

- A Finnish script for the onboarding sample project (a 3-minute interview about pruning an apple
  tree, with planted edits to practise on) is in `docs/onboarding/`; it still has to be recorded.
- Building blocks for later features, not visible yet: which range loops (marks, selection or
  clip), fitting track heights to the window, the loudness-against-target colours, and the maths
  for aligning recordings by sound and choosing which media parts travel with a hand-off.

## [v26.10.18.33] - 2026-10-18

- App icons: the kuulas mark on a dark rounded square, as PNGs (16 to 1024 px), `kuulas.ico`
  (Windows) and `kuulas.icns` (macOS), in `src/kuulas/assets/icons/`, made by
  `scripts/make_icons.py` (which is also the single source of the header logo).
- The desktop window shows the mark on the launcher page, sets the Dock icon on macOS (instead
  of Python's rocket) and passes the icon to the window toolkit. The Dock label still says
  "Python" until the app is packaged.

## [v26.10.18.32] - 2026-10-18

- The kuulas logo (a first version) is in the app: in the header next to the name and as the
  browser tab icon. The desktop launcher and dock icon do not show it yet.

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
