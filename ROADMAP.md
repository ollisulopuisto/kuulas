# kuulas roadmap

## Released in v26.10.30.1 (2026-10-30)

Colab transcription settings now select Whisper large-v3-turbo, Parakeet Ultra,
or a custom model ID supported by the shared `colab-transcribe` tool (WP87). Packaged
Kuulas pins the podcast revision that implements both built-in model IDs. Local
Orukeet is unchanged. WP26 adds pitch-preserving grains above 2× and ruler-drag
scrubbing at pointer velocity. WP23a includes only backend high-pass plumbing
for plain 1× playback; it has no UI and is not yet verified for real-time use.
Owner listening for shuttle and a live Colab run remain verification items.

**Release v26.10.27.2:** GUI Orukeet install/select/reinstall with verified downloads, progress and cancellation; aligned transcription actions; persistent fast-listening button.

**Release v26.10.27.1:** local Orukeet, NHSX import from the start page, a three-second LUFS meter, compact track headers and transcript search, clearer toolbar buttons, and corrected Auto-Silence boundary trims.

## Released in v26.10.29.2 (2026-10-29)

Built from current `main`, including PRs #89–90 and the clipboard mute fix.
Copied clips are unmuted for reuse; Cut preserves the mute state. The whole-
session mastering acceptance case guards export behavior. The separate native
Viewer restricts playback to conformance-covered states and is not part of the
editor DMG.

## Released in v26.10.29.1 (2026-10-29)

Built from `a4cfeae`, current `main` at release time. This release includes the
read-only track inspector values and queued/cancellable local Orukeet jobs
(PRs #83–86), playback LUFS wiring and independent live output RMS, with
transcription status kept visible in compact windows (PR #87). The release DMG
passed both the built-app and mounted-image self-tests. PR #88's native Viewer
playback remains preview code and is not part of the editor DMG.

## Merged after v26.10.29.1 (main through 7bb0072)

- PR #89 adds a whole-session mastering acceptance case to catch regressions in
  full-export behavior.
- PR #90 limits native Viewer playback to states covered by its conformance
  cases. The Viewer remains a separate preview app, outside the Kuulas editor
  DMG.

## Next hard work (2026-10-30)

**WP26 implementation is merged.** High-speed shuttle now uses 60 ms forward
grains above 2×, and ruler dragging scrubs at pointer velocity. Engine tests
and headless UI checks pass; the sound and feel still need the owner's listening
check in `docs/M2-VERIFY.md`. **WP23a (WP23) is partial:** the stateful
high-pass plumbing is merged for plain 1× playback, but it is not real-time-ready, has no
UI, and still needs native callback profiling and listening. WP18 cut candidates
follows in M3 because its recording-clock anchors are reused by later editing
work. WP21's schema migration and WP16's alignment remain later high-risk
packages.

A multitrack **editor** for spoken word: podcasts, interviews, radio. It is
for editing, not recording. The model is Hindenburg PRO: keyboard-first,
speech-aware, with the transcript and the audio as one thing.

Out of scope: loopback, publishing integrations, anything but basic recording, spectral repair/spot healing, music remix/retiming.

**How it gets built:** `docs/PLAN.md`, in work packages for implementers.

**Toolbar, scripting and hardening, v26.10.26.5:** customizable docked toolbar
left of the track headers with drag-and-drop reordering (WP86); headless scripting guide,
HTTP command catalog, and filler-word removal example (WP53); performance
optimizations in filler regexes and bus lookups; extended test coverage for recorder
naming, WAV header generation, PCM24 conversion, and sample-rate validation.

**Playback/navigation, v26.10.26.4:** live anchors preserve manual Follow
detachment; startup corrections do not move against playback while audio is queued.
The overview has at most four round timestamps in a top band. The recorder
acknowledges quit before closing sockets. Browser checks cover three zoom levels;
owner audio-device confirmation remains open.

**Maintenance, v26.10.26.3:** recording/import and job paths, temporary JSON writes,
project names and series-file reads have security regressions and stricter checks.
See [the path-access audit](docs/security/2026-10-26-path-audit.md) for confirmed
fixes and intentional folder-selection warnings; the CodeQL alert list is not
claimed clear. Windows UI source comparisons accept native line endings.

## Requirements and state (2026-10-16)

**Build first** (owner, 2026-10-16): R35 the project format above all, then
R39 (i18n), R10, R29, R30, R33, R26i. They lead the build order in `docs/PLAN.md`
(Triage, marked ★).

Priorities set by the user: **MUST** R29 (trustworthy undo), R33 (fast
listening and JKL, in the MVP); **must-fix**
R23, R27 (real Hindenburg pain); **important, later** R24; **high** R10 (keyboard first:
built straight after the UI shell); **needed** R30, R31. Build order and
sizes: `docs/PLAN.md`, section "Triage".

| # | Requirement | State |
|---|---|---|
| R1 | Multitrack editor | core done (model, edits, mixer); UI next |
| R2 | Buses (track groups) | core done: routing, gain, pan, mute; UI next |
| R3 | Signal processing from the podcast pipeline, not reimplemented | done: `speechmix` + `nhsx` imported as path deps (pan laws, speech grid, duck masks, duck envelopes) |
| R4 | Automixer support | ducking → editable track automation done; speechmix chain per track next |
| R5 | Transcription, local and Colab | local Orukeet through the shared podcast CLI (Apple-silicon MLX) and Colab runner built; Colab model selector offers Whisper large-v3-turbo and Parakeet Ultra (v26.10.30.1); faster-whisper removed from local execution and dependencies; GUI model setup built, packaged TLS fix in v26.10.27.4; real Colab run still unverified |
| R6 | Edit audio by editing the transcript, and vice versa | done in core: words follow clip edits; deleting words cuts all tracks at pause midpoints |
| R7 | Clip ops Hindenburg lacks: clip volume, pan, gain automation | done in core |
| R8 | Mac, Linux, Windows | GitHub Actions matrix: full tests on macOS and Linux; Windows editor tests and desktop smoke, with Unix recorder/analysis/transcription workers and macOS automixer and DMG build-script tests excluded; macOS DMG build |
| R9 | Never lose work; smart undo | done: every edit fsynced to SQLite, undo tree keeps branches, drags coalesce |
| R10 | **High priority.** Hindenburg-level keyboard editing; every UI feature ships with its keys | keymap taken from the Hindenburg PRO shortcut list; UI next |
| R11 | Pro Cut Auto-Silence: mute what does not cross the threshold | done in core (speechmix grid + duck masks → implicit source-frame clip ranges; only edited portions become ordinary clips) |
| R12 | Auto crossfade only where non-adjacent audio is joined | done |
| R13 | Media identified by content hash; survives rename/move | done (SHA-256 ids, every seen path remembered) |
| R14 | Per-source mono/stereo; measurements aware of it | done: mono voices constant-power, stereo music balanced, stereo master; speech analysis reads speech tracks only |
| R15 | Select everything from the playhead on (one track / all tracks) | done in core (`clips_from`, `clips_until`, multi-clip edits) |
| R16 | Sync groups: mark clips in sync, move freely, resync any subclip to the main clip | done in core, timestamps only; fixes accidental one-track cuts; membership per media, shared by every edit (v26.10.16.6) |
| R17 | Late sync: mark from clips still in sync, or from file timestamps (BWF) | done in core |
| R18 | Store media as FLAC to save space | in progress: lossless FLAC verified bit-exact for 16/24-bit PCM |
| R19 | Link media in place or copy into the project (like FCPX); optionally move originals into the project package | in progress: link PCM in place, relink by hash, consolidate; moving removes external originals only after the in-project copy is verified |
| R20 | Ingest every audio format and the audio of video files | in progress: ffmpeg decoder |
| R21 | Heavy parallel processing | imports parallel; analysis, transcription, export next |
| R22 | Basic multitrack recording, standard APIs only (CoreAudio/WASAPI via PortAudio), Mac first; foolproof modal record mode: only a 2 s hold stops it, backend keeps recording if the UI closes, no sleep | planned: WP12 |
| R23 | Sync workflow: files imported or recorded together are in sync by default; align any other file by eye and mark it in sync; optional align-by-sound helper for Zoom/phone files (drift, dropouts) | core done (sync groups, default groups at import); helper WP16 |
| R24 | Space never plays a clip list; dropping never trims to in/out; previews loudness-matched | planned: WP17 + plan-wide rules (important, can come later) |
| R25 | Mark possible cuts on the first listen, decide on the second; markers stay on their audio through every edit | planned: WP18 |
| R26a | Edit groups: an edit applies to the whole sync group unless group editing is switched off (Pro Tools, Reaper) | pure logic for partners and edit targets done v26.10.17.6; `Session.edit_target` and the wiring into cut, ripple delete, ripple trim, nudge, move and cut_words done v26.10.19.5 (engine); UI done v26.10.19.6 (Mod+G chip, dashed partner outline, Alt+Mod+X on the group; not seen on screen yet): WP19a, in milestone M1. Rule: time-shifting edits keep the sync group together, other edits touch exactly the selection |
| R26b | Connected clips: music and effects stay attached to a moment in the speech through ripple cuts (FCP) | planned: WP19b |
| R26c | Roles (dialogue / music / effects), stem export per role, Match Loudness (FCP, Audition) | planned: WP19c |
| R26d | Every command bindable, user key overrides, macros that undo as one step (Reaper) | planned: WP19d |
| R26e | Alternative takes in one slot, switched with one key (Pro Tools playlists, FCP auditions) | planned: WP19e |
| R26f | Spot: type an exact time to place a clip or the playhead (Pro Tools) | parser done v26.10.17.9, dialog and key still to do: WP19f |
| R26g | Skimming: hover to hear without moving the playhead (FCP) | planned: WP19g |
| R26h | Markers and regions, batch export of regions, chapter list (Reaper) | chapter-list formatter done v26.10.17.5; rest planned: WP19h |
| R26i | Tab to transient or to word, cycled with one key (Pro Tools) | onsets backend done v26.10.17.4; Tab key planned: WP19i |
| R27 | Copying clips between projects never copies whole source files: reuse by hash, link in place, or copy only the used range plus 2 s handles; importing from another project lets you pick which clips, bits or regions come in | planned: WP20 (must-fix) |
| R28 | Several edits (versions) of the same material in one project, e.g. 1 × 60 min and 4 × 20 min: shared media, transcripts and sync; separate cuts and undo; cut decisions offered across edits | planned: WP21 |
| R29 | **MUST.** Undo you can trust: Mod+Z stays on the current branch, history restores add a step instead of rewinding, undo brings back selection and view and shows what changed | planned: WP8 |
| R30 | **Needed.** Track tags (speech / music; speech-mix was removed 2026-10-19, separating a downmixed multi-person file is out of scope) are all speechmix needs; ducking of mics and music beds from speechmix + nhsx.musicbed; FX layers: real-time, analyse-then-live, or rendered | track kinds, speakers and music ducking done v26.10.17.4 (backend); WP23a high-pass persistence and plain 1× playback are partial in v26.10.30.1; UI, callback timing and real-time safety remain open |
| R31 | **Needed.** Solo overrides mute and is exclusive by default (mute all, solo one at a time); A/B tracks, edits, takes and layer settings with one key, level-matched by default | planned: WP24 |
| R32 | Music report per edit: every piece of music actually heard, with metadata, programme times, duration and background/featured, as CSV and printable table | report, CSV and HTML done, times round up to whole seconds (v26.10.17.1); tag editing, all-edits report and export alongside the audio open |
| R33 | **MUST.** Sped-up listening (toggle normal/fast, pitch kept) and JKL shuttle with slow and fast scrubbing | WP26 engine/UI implementation merged in v26.10.30.1; owner listening check remains |
| R34 | Project settings changeable later, undoably: sample rate (e.g. 44.1 → 48 kHz, every position converted), mono or stereo master, loudness target, export defaults | planned: WP27 |
| R35 | Own project format `Name.kuulas` (package folder): shared material (media, sync, transcripts) apart from per-edit state; recording facts in flicks so they survive rate changes; versioned with forward compatibility; crash-safe, locked against two writers, automatic backups; lossless Hindenburg round trip | done: WP29 in v26.10.16.5 (package, manifest, lock, v1 schema, material apart from edits, UUIDv7 steps, checkpoints, backups, v0 migration, `kuulas info`), WP30 in v26.10.16.6 (recording facts in flicks, sync groups per media in material); Hindenburg import done (WP13, v26.10.16.14); export back to Hindenburg still open |
| R36 | Focus mode: F focuses a speaker's tracks, the others shrink to strips that keep sync visible; Shift+F also solos; transcript dims other speakers | planned: WP28 |
| R37 | Review round trip: A sends v1, B edits (some changes done, some as suggestions), A gets v2 and accepts or rejects each; works even if A kept editing; hand-off copies carry only used audio | designed: docs/FORMAT.md; build WP31 (changes view), WP32 |
| R38 | Voice condition as a sub-choice of speech ("Speech · remote"; never music): clean / room / remote / phone / auto picks a speechmix preset; auto-suggested from measured noise floor, bandwidth, echo and clipping | waits for presets in speechmix (podcast repo); kuulas side in WP22 |
| R39 | Internationalisation from day one: English and Finnish complete, one catalog for Python and UI, speechmix's messages translated too; locale-aware numbers, Helsinki times with zone, platform key names | WP33a done in v26.10.16.4 (Python catalogs, `messages.t`, speechmix translator); WP33b done in v26.10.16.12 (`ui/i18n.js`, locale endpoint, AppleLanguages); the language setting's screen waits for WP27; the `ast` scan still covers raised exceptions only |
| R40 | Fault tolerance: a bad file or device costs that file or a second of audio, never the session; decoders time out, plug-ins run isolated, the audio callback never fails, device changes are handled | playback side done (WP2, v26.10.16.8; not yet run on hardware); import side WP34 |
| R41 | Snappy UI, multithreaded throughout: heavy work never blocks; edits under 50 ms; 60 fps; no underruns during heavy jobs; background jobs yield to interaction | API and engine done (WP2, WP3: edit round trip 14 ms on the heavy hour); UI render budgets in WP4; jobs done (WP9, v26.10.16.14) |
| R42 | Smart caching: everything derived from a recording is computed once and survives every edit; one memory budget | planned: ground rule 15, WP36 |
| R43 | Remembered settings; quick actions without repeated dialogs; helpful messages with Undo | planned: ground rule 16, WP35 |
| R44 | Navigation: time zoom with snap levels, Z toggles close/wide view, waveform and lane height zoom, scrolling, overview, follow modes, clear keyboard focus | planned: WP4 |
| R45 | Single-key shortcuts for editing (as in Hindenburg); Mod only for file and app actions | planned: WP5 |
| R46 | Autosave on every edit; Mod+S saves a named version; exports are versioned (v1, v2…) without overwrites, skipped when unchanged, traceable | export versioning done (WP11, v26.10.16.14); autosave/named versions planned: WP5, WP31 |
| R47 | Export the whole edit or just a selection; export each track as its own aligned file (dry or as heard, whole or selection) so you can edit in kuulas and mix in Logic | done: WP11 in v26.10.16.14 (API; export dialog is UI work) |
| R48 | Series: material reused across episodes is tracked even when the other project is closed; badges, series view, unused material, cross-series search; published only when marked | usage extraction done (WP37, v26.10.16.14); series files and views planned (WP38) |
| R49 | Portable projects: user B opens user A's project with different paths; relink once and the rest follows, always verified by hash | done: WP39 in v26.10.16.14 (not yet tried across two real machines) |
| R50 | Long history stays fast: keep every step forever, open under 1 s, incremental backups, thinning only if a speed budget fails | planned: WP40 |
| R51 | Sync states made explicit: free from sync on purpose (U, or answer after Alt-drag) vs. undecided drift with its cause; never auto-resync | done v26.10.19.5 (engine: `Clip.free`, `sync_state.py`, drift list and cause from history, resync skips free) and v26.10.19.6 (badges, U, Alt+Cmd-drag prompt, drift list in the Markers tab with ] [; not seen on screen yet): WP19a |
| R52 | Session markers in history; undo across sittings says so | planned: WP8 |
| R53 | People and interviews in the data from the start: who speaks in every transcript, one interview linking all its recordings from different people, everything a person said across the series | data model done in v26.10.16.13 (WP41); person view and cards later (WP42) |
| R54 | Index cards like Scrivener: bits of interviews dragged into episodes, assembled into a timeline; person view | planned: WP42 |
| R55 | Narration placeholders: script text in the timeline with estimated length, optional speech preview, script export, recorded or imported later in place | length estimate done v26.10.17.5; rest planned: WP43 |
| R56 | Auto-Silence stays implicit until edited, belongs to the measured clip, and materializes only the portion the user changes (owner, 2026-10-24) | done in core: source-frame clip ranges; M and edge dragging create ordinary clips |
| R57 | Compare: non-destructive previews and A/B by listening (cuts, values, tracks, takes, edits, voice presets), level matched, blind mode, keep one or discard all | planned: WP45 (builds on WP24.2) |
| R58 | Extensive clipboard with history: cut copies and ripples, delete leaves the gap, entries kept as references, a Clipboard panel, four paste forms, across projects | planned: WP46 |
| R59 | Contextual help from v1 (help key for the focused thing, hints and keys in menus, searchable help index, translated help as data) | planned: WP48 |
| R60 | Onboarding (first-run welcome, sample project, guided tour, progressive tips) | planned later: WP48 |
| R61 | The waveform drawn at its real size: clip gain and track gain change its height (owner, 2026-10-18) | requested: WP57 |
| R62 | Clipping shown on the waveform (red) when the clip or track gain makes it too loud (owner, 2026-10-18) | requested: WP57 |
| R63 | A second edit in the same project called "Selects" that shares the recordings: mark bits while listening, order them, pull them into the story (owner, 2026-10-18; last on the feature list) | requested, last: WP58 (needs WP21, WP17, WP42) |

## Done

- Project model in integer frames; immutable states; JSON round-trip.
- Edits: tracks, buses, clips (add, move across tracks, trim, split, delete,
  gain, pan, fades, mute, envelope), track automation, ripple delete with
  crossfades and continuous automation, mute ranges, selection-wide edits,
  sync groups.
- History: SQLite (WAL, `synchronous=full`), whole state per node, undo tree,
  redo follows the newest branch, `goto` any node, coalesced drags,
  transcripts stored once per revision.
- Mixer shared by playback and export; constant-gain crossfades.
- Analysis: Auto-Silence and automix ducking through speechmix.
- Transcript mapping and word-cut ranges.

## Earlier build snapshot (25.10.2026; superseded by v26.10.29.1)

Release v26.10.24.3 fixes M on the audible openings between Auto-Silence stretches, adds dotted-boundary editing for those openings, and keeps double-click reserved for its specialized actions. The tag workflow builds and uploads the Apple-silicon test dmg. **Built since v26.10.20.39, none of it seen on screen yet** (everything below is committed on main; details and limits in each Next item and in docs/BUGS.md #106-#115):

- **Transcript:** shows only what is heard; Find lists removed material ("Not in this edit"); Put back (ripple insert on all tracks at the seam).
- **Recording:** the take is drawn on its lanes while it records (new tracks are made at Start; the view follows the head); editing is paused during a take (markers allowed); markers while recording (Cmd+Enter, Add marker button); the stop notice says how much audio the take replaced; **the cart** (seven numbered Clipboard slots, Alt+1..7 play, Shift+Alt+1..7 assign) and clips played during a take are logged on a chosen track; a lost Colab session retries once; Colab progress comes from the tool's `--events`.
- **Editing and views:** M on an auto-silenced stretch opens just that stretch as a clip; hold Cmd/Ctrl while moving a clip to snap to ducking ramps and silenced-stretch edges; the Clipboard can be reordered by dragging; a stronger in/out band; focus mode keeps the other lanes readable; closing a toast keeps later ones in the status bar.
- **Windows and files:** Copy to other window; a project open elsewhere is read-only with a banner naming who holds it, and opening it again brings its window forward; File > Export cut list (JSON); the Material tab (Cmd+6); side tabs on Cmd+1..6; Mac key glyphs in menus; Ctrl+click on a Mac is the context menu.

**Built 24.10.2026 after v26.10.24.3 (on main, pushed; dmg run 40131975902; none of it seen on screen):** the menus regrouped (File Versions and More exports, Track Role and Bus, Text Placeholders, Playback Speed, View Options and History, Help > Getting started; question 6, Settings in a native app menu, still open); **Level blocks is a side panel** (stale after an edit, Apply off until Measure again) with a progress bar; the menu bar flashes the menu of a command run with a key; a muted clip shows a crossed-out speaker; **toast text can be selected and copied**; **clip borders are a neutral grey apart from the waveform** (Codex task C6); **M acts on the Auto-Silence portion under the cursor** also for a grouped clip and with nothing selected. The FCPXML summary for the package author is in docs/PODCAST-MAGIC.md.

Waiting on the podcast side: the shared `fcpxml` package (what Kuulas needs is at the end of docs/PODCAST-MAGIC.md), the six `--events` field requests, and the older wishes below.

Open question: should bus gain also reach the automixer stems (like track gain since v26.10.20.14)?

Parked with findings recorded: history compaction (see Next).

Older, still open: media store (linked vs working FLAC, relink, consolidate); browser UI shell (keymap WP5, design redone).

## Milestone 1: what is left to confirm (updated 21.10.2026)

M1 is 23 of 28 done, 5 partly (WP4, WP5, WP19a, WP46, WP6). All are built; the "partly" marks are stale PLAN status lines plus owner confirmation still missing. From `docs/M1-VERIFY.md` (rows the owner has not reported or that changed since):

- [ ] **3 Import:** WAV and MP3 through File > Import, a drop from Finder onto a lane, a bad file gives a clear message (only mp4 and an mp3 drag are confirmed).
- [ ] **4 Loop:** the loop button shows clearly when on (built v26.10.20.16).
- [ ] **6 Copy, cut, paste** and the Clipboard tab: never reported. Since then: paste modes (v.17), series/shared shelves and drag from the panel (v.38).
- [ ] **7 Mouse editing:** drag a range, move a clip by its label strip, trim an edge, Cmd+click select. Retest dragging a synced clip to another track (partners no longer move, WP83; BUGS 91) and Cmd+drag trim of one clip (BUGS 97).
- [ ] **8 Sync R:** edge cases; the "hole after moving a synced clip out and back" needs your decision (BUGS 84).
- [ ] **11 Export:** the dialog now has range, tracks, name, format and loudness (BUGS 92); check MP3 settings, whether mute/solo count, and that the default is FLAC (v.37).
- [ ] **12 Cheat sheet and Finnish keys:** Help > Pikanäppäimet; no key needs AltGr or Shift+digit; Shift+Cmd+K search.
- [ ] **14 Clock digit entry** from the right (built) and **16 faster menu hover** (90 ms, built): retest.
- Outside the list but blocking "confirmed": BUGS 83 (clips could not be moved: needs your exact symptom), BUGS 81 (dmg "damaged" until quarantine is cleared: needs Apple signing), BUGS 3 (Dropbox lock never tried on a real Dropbox), BUGS 80 (Cmd+M gone).
- Housekeeping: update the PLAN status lines of WP4, WP5, WP6, WP19a, WP46 ("Status: open. Needs WP4" is stale for WP6) when you confirm them, so the milestone count can reach 28 of 28.

## Right-click menus and track order (built 2026-10-25, not seen on screen)

- Done: track drag handle + Track > Move track up/down (Alt+Cmd+Up/Down); loudness readout on the header's level row; header menus show keys; clip menu reordered (key-repeat steps dropped, Match loudness added); track menu offers one of Group/Remove-from-bus plus Select all, Focus, Move; new menus for placeholders, picked transcript words, Clipboard rows, ruler markers.
- Also done: right-click on a marker flag / region bar (ruler hit-test `markerIdAtX`) and on a clip volume-line point (`clip.envelope_delete_point`, `clip.envelope_reset`). Also done: ducking-point menu (`automationPointAt` hit-test in `ui/lanes.js`, `track.automation_delete_point` / `track.automation_clear`) and the transcript right-click on an unpicked word. Not done: dragging ducking points (the curve is still only written by Track > Auto). A selection strip (Opus: only if buttons are still wanted after trying these) is not built; floating tool palette: decided no.
- Check on screen: drag handle feel (drop position while dragging shows only an outline), loudness text on the level row at rest (hidden until hover / current track in the comfortable density), compact headers (dot in the corner).

## Released in v26.10.25.4 and .5

- v26.10.25.4 (tagged 2026-10-25): sync drift marks hidden by default; range commands (below).
- v26.10.25.5 (tagged 2026-10-25): security fix, CodeQL 58: a window only opens for a real *.kuulas folder.

## Sync drift display and range commands (built 2026-10-25, not seen on screen)

- Done: sync drift badges hidden by default; View > Options > Show sync drift shows a dot / rings plus a tint instead of ms numbers (Codex C10, merged); Clip > Sync back > Resync the range / Accept the offsets in the range (range = in/out marks, else cursor to end; only drifting clips).
- Not done: treat a clip moved by hand after the sync was set as accepted automatically (risk: hides a real drift); the range commands ignore the "selected tracks" scope (they act on all tracks).
- Check on screen: that the tint and dot read in both themes and on narrow clips; Accept on a real half-remote session (the one in the owner's screenshot, 2026-10-25) leaves nothing flagged after it.

## To try in the dmg of 2026-10-26 (all built today, none seen on screen)

1. **Toolbar rail (WP86):** ten buttons, the Search button on top, View > Toolbar (show, icons or text, reset); drag a button to a new place (a line shows where, Esc cancels), Alt+Up/Down on a focused button; right-click a menu row, Add to toolbar; right-click a button, Remove. Check that no button ever moves by itself and that it survives a restart. Auto-Silence badge: run Auto-Silence and read the count. Hint: mute by hand ten times and look for the one notice (once only).
2. **Transcript:** the find field is always there; select words and drag: the pop-up must not cover them; I then click elsewhere (an implicit O), and the other way round.
3. **Auto-Silence in the timeline and overview:** the hatching (is dark mode too faint?), dragging an implicit portion moves only that portion and makes it a clip, timestamps on the overview (up to four round ones), menus and tooltips stay inside the window, tooltips stand out.
4. **Scrolling while playing:** scroll the timeline past the playhead; Follow stays off and the window does not jump. The transcript scrolls freely and playback does not capture it.
5. **Scripting (WP53):** `GET /api/commands`; `python scripts/examples/remove_fillers.py <project> --dry-run`, then for real: one undo step per cut, and the session opens in the window for adjusting.

## Newer things to try (since v26.10.20.39; the dmg of 24.10.2026)

1. **Recording (needs a real microphone):** two channels onto existing tracks, then onto new ones; watch the live drawing and the view following; Cmd+Enter drops a marker; try an edit during the take (it should say editing is paused); stop and read the notice; record over audio and check "It replaced ..."; choose a cart track in the setup, play a clipboard clip with Alt+1 and see it land where it was played.
2. **M on a silenced stretch:** put the cursor in an Auto-Silence stretch (also on an audible opening between two) and press M, with one clip and with a group selected, and with nothing selected; M again toggles just that portion. Drag a dotted boundary: it becomes a real clip that Auto-Silence leaves alone.
2b. **New since 24.10.:** the regrouped menus (look for anything you cannot find), Level blocks as a panel (edit while it measures), the speaker icon on a muted clip, copy text from a toast (Cmd+C), clip borders in light and dark.
3. **Cmd (Ctrl) while moving a clip** near a ducked music track: marks along the top, snapping to ramp ends.
4. **Clipboard:** drag entries into a new order (Paste reads the first); the number chip and Alt+1..7; Shift+Alt+n assigns.
5. **Material tab (Cmd+6)** and its Place on timeline.
6. **Two windows:** two episodes, Copy to other window; the same project opened twice (read-only banner, bring-forward).
7. **Toasts:** press X on a progress toast, look at the status-bar button. **Focus mode** (Shift+F) and the in/out band, light and dark.
8. **Colab:** one transcription from the dmg (also with a stale session): steps in the toast.
9. **Side tabs** Cmd+1..6, and that Cmd+1/2 no longer set marks (I and O do).

### Earlier list (v26.10.20.35 to .39)

Silence visuals (outline, padlocks, dashed ends, group outline); missing media and Relink; Mic kept open row; Series dialogs and status chip; Focus mode (Shift+F); Automix range and Rendered mix; Auto-Silence panel and learning its Sensitivity from muted clips; Keep my music levels; Clipboard shelves and drag; side tabs on one row with Alt+1..5 hints; overview bar with gaps; History saved versions and filter; Follow playhead (the last three in flight).

### Older list

Released in v26.10.20.5 to v26.10.20.14, in order of importance:
00. **v26.10.20.8-.14 (new, nothing tried yet):** (a) the Aame mix: export again, Aame's track gain now reaches the automixer (v.14), check the balance against Kuulas; (b) Track > Auto > Level blocks (listen for clicks at the new cuts, real speech untested); (c) bus roles: bus header right-click > Role, '!' badge on a track, asterisk and Reapply on a bus, Inspector dropdown 'Match bus role'; (d) Cmd (Ctrl) + drag on a clip edge trims only that clip; (e) automix progress shows '3/4 track 2/3 Kari: debleed (2/9)' and 'skipped' for switched-off stages; (f) Music level field default +1.
0. **v26.10.20.7 (new, nothing tried yet):** Track > Auto > Set music level (numbers shown, one undo); backups compressed and Statistics > Size; automix Music field + 'Done in Kuulas' badge/Reset/offer (layout and the 'Set music level again' link only unit-tested, never seen in a window); `Done in Kuulas` line in log.txt. The local dmg build into ~/Desktop/kuulas-dmg came out empty; cause not found (needs the script's last output); the GitHub dmg is fine.
1. **Automix log (v26.10.20.6):** after an automix export a `log.txt` sits beside the wav; the notice has 'Show log' and the 'beds: ... mastered: ...' lines. Send the beds line: it tells how much the music was raised (music came out far too loud; the automixer forces the beds to 1 dB under the speech).
2. **Memory on the 47-minute project:** Kuulas under about 2 GB in Activity Monitor; at most one small `analysis_worker` process (`ps -axo pid,ppid,stat,etime,rss,command | grep analysis_worker | grep -v grep`); a killed worker is now an error, not an in-app run.
3. **Paste:** Cmd+V overwrites on the selected track; Alt+Cmd+V inserts; with In/Out marked it fits the range.
4. **Clipboard:** play a clip, button turns to Stop, progress bar, square buttons.
5. **Click and selection:** clicking a clip highlights and selects its track; dragging a group outlines every member.
6. **Keys:** Cmd+1..6 (Ctrl+1..6 off the Mac; was Alt+1..5 until 2026-10-23) side-panel tabs (not while typing in a text field); Esc closes the top dialog, Enter accepts (safe default in confirmations).
7. **Automix dialog:** collapsible groups with chevrons and badges; fuzzy plug-in field (type 'dxrev'); the block-level hint.
8. **Export names** start with the project name (not 'Pääeditio').
9. **Looks:** buttons all one style, dialogs and panels aligned in one form grid (headless-Chrome screenshots only so far).
10. From v26.10.20.4: stop and cursor at 1.5x to 2x, settings remembered (fast speed 1.75), Cmd+V on the selected track, quick mute H, Cmd+1..9 on the start screen, music tracks not transcribed.


## Next

- **Edit keys never fail silently** (built 2026-10-22, not seen on screen; is the OS beep really gone? owner 2026-10-21): (1) when X, Backspace, Alt+X, copy etc. cannot act, show a one-line reason instead of a clank ("Nothing to cut: mark a range with I and O, or select clips"; en+fi; the same for "no tracks selected", "everything already muted"); (2) editing keys are global except in text fields and modal dialogs, and after an edit succeeds the focus moves to the timeline so the next key works; (3) keep Shift+X unbound; (4) the Escape fixes from the audit (scratchpad/escape-audit.md): the transcript word-range Esc must not also run goHome, Esc must not cancel a running export (the notice has a Cancel button), an empty clipboard filter's Esc must fall through, Auto-Silence preview Esc consistency, tests for goHome/drag cancels/menus, update ROADMAP:163, cheat sheet and `ui.hint.home`.
- **Shortcut audit decisions** (owner 2026-10-21, from docs: scratchpad/shortcut-audit.md; apply as one change set later): keep ours over Hindenburg: Cmd+F find (HB: fade), F fit selection, 0 fit view (the HB marker-jump keys 3-9 are not wanted: owner only uses go to in/out), Alt+3/4 side tabs, the paste defaults (Cmd+V overwrite on the selected track, Alt+Cmd+V insert: "better than Cmd+I"), Cmd+D select none (HB: duplicate; Kuulas has no duplicate command: add one only if wanted), Alt+G clip fade, sync point 1/2, the clipboard model (no numbered clipboard), marker next/previous, Cmd+L Duck the microphones (HB auto levels: ours is better), Import and Export as they are. Done now: merge clips = Shift+Cmd+M (HB key). Done: Shift+Space stays play-selection-once (Hindenburg), Alt+Space = loop the selection; Cmd+H in Hindenburg is zoom to selection (ours is F; Cmd+H is the macOS Hide key, so it stays unbound). Open: Escape per mode (audit requested: scratchpad/escape-audit.md), the P1 audit findings (X family only on the timeline, Shift+X unbound, Alt+U for free from sync, Alt+B for split-all).
- **Exports honour the selection** (owner 2026-10-21; not started): every export (Cmd+E quick, automixer, options, stems, music report scope too) exports only the selection when there is one: in/out markers, else the selected clips (their time span); the UI says so explicitly ("Exporting the selection only: 12:00-18:30" in the toast/notice and in the dialog), the default file name carries it (like the automix range names: "<name> ... 12.00-18.30"), and the options dialog has a toggle "Only export the selection", ON by default when a selection exists and switchable off.
- **Save = a saved version** (built 2026-10-22, not seen on screen; owner decision 2026-10-21): **Cmd+S** makes a saved version named by time ("Saved 14.32") and shows it in History; if nothing changed since the last saved version it makes none and says "Already saved at 14.32" (no duplicates); it no longer makes a backup copy (the 10-minute timer keeps doing that; optional File > "Back up now", no key). **Shift+Cmd+S** asks for a name and makes the same kind of version. **File > "Open earlier version…"** opens History with the Saved versions switch on (command `history.open_saved`, with the hint that any step can be restored). Optional later: expire unnamed timestamp versions after ~30 days, a "Named only" filter. Fix help/strings that still say Cmd+S makes a named version.
- **Music anchored to speech ("connected clips")** (owner 2026-10-22: chosen instead of a hard picture lock; design note first: docs/design/MUSIC-ANCHORS.md): every music/effects clip is attached to something: a word, a speech clip's start or end, a marker, or plain time. When the speech edit changes (cut, ripple, Put back, trim), an anchored clip follows its anchor instead of blindly following time; if its anchor disappears (the word was cut) the clip is marked "check". Like Final Cut Pro's connected clips. A light "speech edit locked" warning state for a version may come later, only if anchoring is not enough.
- **Two windows, two episodes: moving material between them** (owner question 2026-10-23; planning agent's reading of the code, not tried on screen; one process already runs many windows, each with its own server, desktop.py:710-790). Today: Copy in A, in B Clipboard > Other projects > expand A > Paste (4-5 actions); "Other projects" is not live (read when opened). **Done 2026-10-23, not seen on screen (the P0): the same episode must not open twice** (owner: no two windows on one episode until a full versioning system exists, and then they would be different entities): the check compares raw path strings, the launcher skips it, and the same-process lock is ignored, so a second window gets a writable Package; the SQLite file survives (WAL) but the history tree forks (each window keeps `head` in memory). Fixed by the lock itself (`package._lock_holder` no longer skips the same process; a second open is read-only) plus a banner that names who holds it (`/api/state` `read_only`, `ui/read-only-model.js`). Also fixed 2026-10-23: the same folder reached through a symlink, alias or the start page of another window brings the first window forward (`WindowApp.bring_forward_if_open`, resolved paths). **Then, ranked:** (1) live "Other projects" with open windows pinned; (2) **BUILT 2026-10-23, not seen on screen**: Edit > Clipboard > "Copy to other window..." (copy in A, adopted into B's clipboard, B says "1 entry from Ep1: Paste"; 2 actions, reuses clipboard_adopt and hash-checked paste); (3) drag across windows: **declined by the owner 2026-10-23, not needed**. Open for the owner: refuse or read-only viewer for a second open; does Copy to other window paste at once or only fill B's clipboard; a "Move to other window" (Cut + send); which key (Finnish layout); (drag: declined). Cut in A and Paste in B are two independent undo steps; B then depends on A's file paths.
- **Kuulas to autoraffkat (video rough cut from a Kuulas edit)** (owner idea 2026-10-23; design thinking by an Opus agent, nothing built; Kuulas has no Final Cut XML export today). Goal: make the content edit once (in Kuulas, by ear and transcript), then get a multicam rough cut that already matches it, with the camera on whoever is really heard, instead of redoing every content cut by hand in Final Cut and letting autoraffkat guess the speaker from raw loudness. **Signals, by value:** the edit decision list on the recording clock; Auto-Silence gates (closed = not this person, only bleed); transcript speaker labels and word times; overlaps; markers/chapters; person identity per series; soft cuts (silent but still on screen). **Noise for picture:** muted coughs and asides (the face is still there), unaccepted candidates, music and ad clips (no camera), ducking and gain curves, undo history, shelves. **Does not transfer:** sample-accurate cuts (picture snaps to frames; use split edits), room tone (a listening face, not black), audio crossfades (stay hard picture cuts), fine "umm" cuts (many tiny jump cuts: cover with an angle change or ignore for picture). **Stumbling blocks:** who owns the timeline after the rough cut exists (the picture-lock problem; hand fixes in Final Cut are not re-imported), whose sync clock is truth, camera scratch audio must be in the sync group, media paths, frame rate and drift, versions in file names. **Three experiences:** A edited timeline only (cut list on the recording clock; autoraffkat keeps its loudness logic); B = A plus a speaker-activity file (heard-speech intervals, overlaps, markers) that replaces loudness; C Kuulas shows camera choice (rejected for now: scope creep, kuulas stays an audio editor). **Recommended start: A, shaped so B slots in**; test on one real Peter & Peter episode (jump cuts left, hand fixes, sync at start/middle/end, B vs loudness on the five worst bleed stretches). Open for the owner: is the video always cut to the finished audio; will audio be re-edited after the rough cut (is losing hand fixes acceptable); whose clock is truth; what to do with fine cuts; is the final mix one file dropped into Final Cut; what to show for music/ads/intros; should a muted cough or gated listener ever trigger a reaction shot; Final Cut only or Resolve too (OTIO unchecked); prior art unchecked (Descript, Riverside, Premiere auto multicam, AutoPod). Next step: Kuulas needs an FCPXML (or OTIO) export of the edited timeline first.
- **Final Cut XML in and out (FCPXML)** (owner idea 2026-10-23; prior art and plan by an Opus planning agent, nothing built, plan not yet approved by the owner): import the FCP timeline the owner syncs (FCP's sync becomes the truth), edit the audio in Kuulas, export an FCPXML of the edited timeline for autoraffkat. **Prior art (agent's search, partly unverified):** OpenTimelineIO's fcpx_xml adapter (Apache-2.0) covers tracks, audio, gaps, markers but not transitions, multicam or sync clips (flattens containers; not a core); PyPI `fcpxml` says do not install; the Swift libraries are macOS-only; Descript has no FCPXML round trip; so **reuse autoraffkat's own reader** (MIT, read.py 984 lines: sync-clip, project spine, mc-clip, ref-clip, audition, muted roles; coupled to its i18n/model/probe/relink, to be cut loose). Its writer (2298 lines) is camera-segment specific and not reusable. **Plan:** new shared package `podcast/packages/fcpxml` (MIT, stdlib only, consumed like nhsx/speechmix; separate repo, wishes only) -> Kuulas `fcpxml_plan.py` (pure mapping) -> `Session.import_fcpxml` (one History commit, menu + palette + en/fi) -> cut-list extraction on the recording clock -> `conform` writer (new project spine made of pieces of the original containers, resources copied verbatim, cuts snapped to frames; video, sync and roles never pass through Kuulas's model) -> Export > Final Cut XML -> end-to-end test in autoraffkat and FCP -> later experience B (sidecar file with gates, word times, speakers, overlaps). **Mapping:** assets -> media by path + SHA-256, link only never copy (recordings stay untouched); video assets use their first audio stream (R20 gap: other streams are lost); clip times from exact rationals (1001/30000 s) to flicks, rounded once, never accumulated; one SyncGroup per FCP sync container (a media can be in one group only); `dialogue.<sub>` roles -> speech tracks with the speaker, music/effects -> music tracks, camera scratch audio -> its own muted track kept in the group; muted roles -> muted clips; audio transitions -> crossfades; markers kept; compound clips and auditions flattened; clips with timeMap/conform-rate refused and reported; the original XML kept in `Project.extra`. **Tests to write first:** rational-to-flicks exactness (1001/30000, 100/2500, /5644800), a synthetic 2-hour 29.97 timeline within 0.5 sample, group origins equal the FCPXML offsets, round trip through autoraffkat's reader, fixtures from autoraffkat tests/make_fixture.py and podcast/vertical2.fcpxmld, fault cases (garbage XML, bundle without Info.fcpxml, missing media, video without audio, two audio streams, %20/ä/Windows file URLs), hashes of recordings unchanged; manual: cross-correlate camera scratch audio against the mic to confirm sync within 1 ms (catches AAC/MOV priming offsets). **Risks:** media paths (macOS bookmarks override src), AAC/MOV offsets, multicam angles with gaps or several parts, FCPXML versions 1.8-1.14 (write the source's own version), a media under two clocks, hand fixes in FCP lost on re-export (picture lock). **Owner answers 2026-10-23:** the FCP export is a project **timeline** (not multicam or event sync clips); music is **kept** in the export, ads are not a concern now; **Resolve support wanted if it is easy** (Resolve imports FCPXML, reportedly preferring 1.8-1.9, unchecked: write the source file's own version and try); **one way only**: import once, export once, no two-way sync (later audio changes after picture work are the video editor's problem, so hand fixes in FCP are never merged back); a trimmed real episode fixture **later**. **Later answers 2026-10-23:** the export carries the cut mic clips as **separate tracks** (the point: give autoraffkat more data); the owner finds FCP roles mostly irritating, so **roles are only a suggestion** (FCP role -> a Kuulas bus of that name with kind speech/music, sub-role -> speaker, always editable in the import report; never required): a robust split without roles is that an audio-only asset is a mic and an asset with video is a camera's scratch audio. **Frame-perfect export, with cover shots:** the owner's own practice is that a run of audio edits on one speaker is hidden in the picture by one unbroken reaction shot of the other camera on top. So the export must tell autoraffkat WHERE the audio cuts are (jump-cut points), so autoraffkat can lay one cover shot across a cluster of cuts instead of many tiny picture cuts. Wish for the podcast side: a cover-shot rule (a run of N cuts within S seconds on one speaker becomes one other-angle shot; autoraffkat's reaction logic is the starting point). Picture cuts land on frames; whether audio cuts may stay sub-frame in FCPXML is unverified and must be tested in FCP. **Priority (owner 2026-10-23): hiding the cuts of one speaker is the most important thing this whole chain can do**, because autoraffkat cannot do it today (it only knows loudness, never where the audio was cut). So the value order is: (1) the list of audio cut points on the program timeline, per speaker, which only Kuulas knows; (2) autoraffkat's cover-shot rule that uses it (when one speaker's camera is on screen and their audio has cuts, put one unbroken shot of the listener or the wide over the run, instead of a jump cut; a single cut or a cut inside silence needs no cover); (3) the import that makes the two tools share one sync clock. The plan's work order should be reconsidered so that (1) and (2) are shown on one real episode as early as possible, even with a thin import. **Built 2026-10-23, not seen on screen: the cut list** (first slice; `src/kuulas/cut_list.py`, `GET /api/cut-list`, File > Export cut list (JSON), format in docs/design/CUT-LIST.md): per speech track the cuts on the timeline and on the recording clock, seams across tracks, recordings with checksum and clock. Not yet: who is heard when (experience B), the FCPXML import and export, the cover-shot rule (podcast side). **Rule idea (owner 2026-10-23: never a visible jump cut; reuse autoraffkat's shot-length rules; to think through, not decided):** every audio cut is a camera-change point. A cut that already falls on an angle change needs nothing. Where the same camera would continue across the cut, switch to another shot that starts `lead` before the cut and runs `hang` after it (autoraffkat's rhythm presets have both: broadcast lead 0.30 s, hang 0.60 s, min shot 2.5 s; mellow 4.5 s; hectic 1.4 s), and a shot is never shorter than the preset's minimum, so every further cut that falls inside it is hidden too; the next cut after it starts a new cover. So cuts spaced closer than the minimum shot share one cover, cuts spaced wider get one cut-away each, which is the show's normal rhythm. The cover is the listener's camera or the wide; with no second camera (or none free) a punch-in on the same camera is the usual fix (autoraffkat has a reframe module; unchecked). It must also respect the periodic wide shot and never be the speaker's own camera. **Owner refinement 2026-10-23 (lip sync):** any shot that shows the speaker (the wide) keeps running in the original footage while the audio has jumped ahead by the removed time, so the lips drift out of sync for as long as the wide stays on, and the drift adds up with every cut in a run. So: **one cut in a run: the wide may cover it**, held for autoraffkat's wide-shot length values (broadcast `wide_hold` 3.5 s; the minimum shot also applies), and cutting back to the speaker's own camera re-syncs the picture, because that camera is cut with the audio; **several cuts in a run: the listener's close-up** (no lips of the speaker to drift) held across the whole run under the minimum-shot rule. The deciding number is the total time removed inside the cover (the drift the wide would show): up to a small budget (to tune on a real episode, a few tenths of a second is a guess) the wide is allowed, above it the close-up. Wish for the podcast side: this choice in autoraffkat's decision layer, fed by the cut list. **Still open:** the sub-frame question, the cover-shot thresholds (how many cuts within how many seconds; tune on a real episode) and whether a cover shot may use the same camera's wide framing. **Wishes for the podcast side:** the `fcpxml` package; autoraffkat reading `marker`/`chapter-marker`; a flag saying the timeline is already edited so autoraffkat does not cut content again; raw twins and redirection checked with many mc-clip pieces; an agreed schema for the sidecar file; real fixtures with tiny media.
- **Recording view and playback while recording** (owner question 2026-10-23; recommendation, not yet decided): **(1) the modal.** Today Record opens a modal dialog with a meter, elapsed time and a 2 s hold-to-stop; Hide closes it and a toolbar chip shows the take; the timeline behind is drawn live (BUGS #113). Recommended: after Start the dialog steps aside by itself (a slim recording bar with the Stop control and the chip) and the timeline is **navigable but not editable**: scroll, zoom, look, select, add markers (Cmd+Enter), follow the head like the playhead's Follow chip (the view follows until you scroll away, then a chip brings it back); every edit, undo and paste is paused with a visible "recording: editing paused" state. Why not fully free: the take lands at a fixed timeline frame when it stops, so a ripple cut or move before that frame would put it in the wrong place (a recording is never lost, but it would land wrong). Why not progress-only: you want to look around, set markers and read the script. **BUILT 2026-10-23 for (1), not seen on screen, not tried with a microphone:** the dialog steps aside on Start; tracks the take needs are made at Start (one undo step, `RecordSession._make_tracks`); the view follows the head until you scroll away (`ui/live-follow.js`); edits, undo and redo are refused while a take of THIS project records (`History.edit_guard`, `Session._check_not_recording`), except markers and the take's own landing. Still open from the plan: the slim recording bar with Stop (today the toolbar chip reopens the dialog), and a visible "editing paused" state beyond the chip's text and the refusal's message. **(2) material on other tracks.** Today starting a take stops playback (`/api/record/start` calls `engine.stop()`) and nothing is heard; monitoring is the audio interface's direct monitoring (PLAN WP12: playing the existing mix while recording "comes later, with latency compensation"). Recommended order: first the view above; then an opt-in "Play the other tracks while recording" (headphones warning, off by default), which plays every track that is NOT being recorded from the take's start frame, and places the new clips shifted by the measured round-trip latency (the tap-to-click calibration in this file's latency item is the measurement), because a late take against a backing track is the whole point of overdubbing. Open for the owner: is overdubbing against track 1 a real need soon (it decides the order); and do edits really need to be paused, or only the ones that move material before the take's start?
- **Play clipboard entries while recording, and log them on the timeline** (owner idea 2026-10-23, "a Q&A show: the questions are audio files on the clipboard, you play them; it would be super useful to have them recorded to the timeline when they are played"; not started): like a radio cart wall. During a take, firing a clipboard entry (a chip's Play, or a key) plays it out through the output AND puts a clip of it on the timeline at the take's place at that moment (take start + elapsed, as the markers do), on a track chosen once (default: a track called Questions, made if missing), trimmed to what was actually played when it is stopped early. Afterwards the question sits exactly where it was asked, next to the answer on the recorded track, which is the point. **What exists:** clipboard entries already play as a preview through the engine (`/api/clipboard/{id}/preview`, a temporary project, mixed into a playing timeline or alone) and entries paste as overwrite on a chosen track; starting a take currently calls `engine.stop()` and says nothing about previews (unverified whether the output keeps playing while the recorder listens). **Needs:** (1) a short live check that a preview can play while a take records (one process records, the other plays; same device or not); (2) one allowed edit during recording: the log paste, an overwrite on its own track at a frame after the take's start, so it cannot move the take (the rest of the editing stays paused, see the recording view item); (3) a `clipboard.cart` command with chips that fire from a number key row (Finnish layout: no Shift or AltGr, so Cmd+number is taken by the tabs now, so probably the keys 1-9 in the cart mode only, or the Clipboard panel's own buttons); (4) trimming on stop. **Owner answers 2026-10-23:** (1) the questions go on a track that is NOT one of the tracks recording from the input; the owner picks it when starting to record (a pre-selected track in the Record setup), and if that track already has audio from the take's start on, the setup warns ("there is already material on this track, overwrite it?") before Record starts. (2) The played level is NOT the raw level and not the preview's quiet attenuation: it should come out at about the level of the voices people hear (the monitored recording), so the question is normalised to that: gain = (the level of the live voices) - (the entry's own level), limited by the entry's peak. The live voice level can come from the recorder's level events (peaks per channel; crude, a short rolling figure) or, with no voices yet, from the project's reference level (`preview_level.reference_lufs`, WP82). What the interface plays back loudly is the interface's own business; Kuulas matches digital levels. A small manual trim (dB) stays. (3) Keys: Alt+1..9 are free now that the side tabs moved to Cmd+1..5 (Alt+0 is reset speed, Alt+Cmd+1/2 the sync points): candidate keys for cart slots 1-9, matched by key position so they work on the Finnish layout. (4) Routing to a remote guest or to headphones only: the OS's job (a loopback or aggregate output); agreed. **Owner answers, later 2026-10-23:** slot n is a CART TAG, not the Share star (the star shares an entry with every project, a different thing, and starred entries are in no fixed order): from a clipboard of, say, 10 entries the owner tags up to 9, each tagged entry shows its number, and Alt+1..9 plays number n; the same keys play in EVERY situation (recording or not). No silent mode: playing a clip while recording always puts it on the timeline ("if you are playing clips while recording, you want them to be part of the recording"). Not recording, the same key is the plain preview. **Prerequisite the owner wants soon:** the clipboard cannot be reordered today; entries must be draggable into any order (BUGS #115). **Step 2 built 2026-10-24, not seen on screen, not tried with a microphone:** the record setup's "Clips you play go on" (none / a new Questions track / a track that is not recorded onto, with the overwrite warning), `RecordSession.cart_log` + `POST /api/record/cart`, `Session.cart_log` (the one paste allowed during a take, op name `cart_log`), and the logging from `previewClipboard` while recording. Still open: trimming the logged clip when a play is stopped early, matching the played level to the voices, keeping the cart track if the editor window is closed and reopened mid-take, and the live check that a preview and a take really run together on one audio device (the code does not forbid it). **Built 2026-10-24, not seen on screen (step 1, the tags and the keys):** `Entry.cart`, `ClipboardHistory.set_cart`, `POST /api/clipboard/{id}/cart`, the number chip on each row, Alt+1..7 play and Shift+Alt+1..7 assign (`ui/cart-model.js`, `edit-commands.js`), Playback > Cart (it first sat inside Edit > Clipboard, two submenus deep, where the menu bar cannot open it; moved 2026-10-24). **Seven slots, not nine:** Option+8 and Option+9 are the bracket keys of a Finnish Mac, and the keymap test forbids a default key there. Not done: step 2, putting a clip played during a take on the timeline (needs the live check that a preview can play while a take records), the cart track chosen at Record and its overwrite warning, level matching to the voices. **Open:** whether tags are per project or can ride the Shared shelf. **Assigning a number (owner question 2026-10-23: should Alt+n on a highlighted entry assign it? recommendation, not decided):** no. Alt+n must only ever PLAY slot n, in every situation, because during a take a key that sometimes assigns instead of plays (depending on which panel has focus) is a live accident waiting to happen. Assign with the entry itself: a small number chip (1-9, or none) on each Clipboard row that opens a picker, plus a command "Assign cart slot..." in the Edit > Clipboard menu and the palette that asks for the number; picking a number already used moves it (the old entry loses its number), picking none clears it. **Owner 2026-10-23: Shift+Alt+n is fine too, shown in the menu and on the chip as Shift+Alt+n:** it assigns the highlighted (picked) Clipboard entry to slot n, and does nothing when none is picked; Alt+n alone still only plays. The Finnish-layout worry was about characters that need Shift or AltGr; keys matched by key position (Digit1..9, as Alt+n is) do not have it. Caveat to check: on Windows, Alt+Shift is the shortcut that switches keyboard layouts, so Shift+Alt+n may flip the layout there (unverified; Mac first).
- **Recording over existing material and alternate takes** (owner 2026-10-23: "you just want to erase it", "the alternate takes situation, I don't think we've built that"): **today** a take that lands on a track with clips on it trims them back (as an import onto a track does, `Session.import_take_lanes`), only over the span the take covers, as one undo step; the old audio files are never touched, so undo brings it all back (ground rule 17). That is the "punch in and replace" the owner means. **Not built:** alternate takes (keeping the replaced clip as a hidden alternate under the new one, choosing between them, comping a best-of from several; the nearest planned thing is the Selects edit, R63, last on the list). Recommended for now: keep trim-back, and say in the stop notice how much existing audio the take replaced ("replaced 12 s on Olli; Undo brings it back"; check whether it already does), and make the Recordings list (BUGS #82) the way to find any earlier take. Alternates need a model change (a clip with alternates, or take lanes per track) and a design note first; not planned until the owner decides they come before the Selects edit.
- **The project's material list (the Recordings list, WP12e, BUGS #82)** (owner 2026-10-23: "probably the solution we want early on; project properties, or a feature of the clipboard? all the material that is in the project"; not built): recommended as its own side-panel tab, **Material**, not project properties (it is a working list you act on, not settings) and not the Clipboard (the clipboard holds pieces you copied; this lists whole files). One row per recording in the project, including every take: name, length, where it came from, how much of it the edit plays (`source_map.coverage`: used / cut / unused), and actions: Play, Place on the timeline (at the playhead, on a track), Copy to the clipboard, Reveal, Relink. This is what makes "a take replaced by a later take" and "the question I never used" recoverable without Undo, so the stop notice can point there. The same list is the base for the Selects idea (R63) and for the cut/unused search results (Put back). Design note: docs/design/MATERIAL.md. **First version built 2026-10-24, not seen on screen:** `src/kuulas/material.py` (rows from `source_map.coverage`), `GET /api/material`, `POST /api/material/{id}/copy` (the whole recording as a clipboard entry), the sixth side tab (Cmd+6, `ui/material-panel.js`, `ui/material-model.js`) with the four filters, a name search, Copy to clipboard and Place on timeline. **Not done:** takes in `recordings/` that were never put on the timeline (the project's media list does not know them), grouping a multitrack take under one header, Play on a row (play it from the clipboard entry), Reveal and Relink on a row, selecting a row to show where it is used, and "Remove from the project".
- **Volume automation points and gate edges as snap targets** (owner idle thought 2026-10-23: "move my dialogue clip to start just at the point where I ducked it down manually"; not decided, not built). Today a moved or trimmed clip snaps to other clips' edges, the playhead and the in/out marks (`ui/move-snap.js moveTargets`); automation points, envelope points and closed-stretch edges are not targets. **For:** aligning speech to a duck (or a duck to speech) without guessing frames; trimming a clip to where a fade or envelope returns to level; cutting at the edge of an Auto-Silence stretch; aligning a clip on one track to a level change on another. **Against:** the automixer writes hundreds of points per track, so every drag would catch on something; a duck is a ramp with two points and it is unclear which one is "the" border; moving speech to fit the duck is circular when the duck was made from the speech (move the speech, then re-run the ducking); invisible snap targets surprise unless the snap line is shown (it is). **Recommendation:** add them as an opt-in kind of snap target, not tab stops: only the significant ones (a level change of 3 dB or more: the end of a duck ramp, the start of the release, and the edges of closed stretches), drawn as small dots while a clip is being dragged, lower priority than clip edges, off with Alt like the others, switchable under a "Snap to:" choice (clip edges, marks, playhead, level changes, silenced stretches). Needs a short look at real automixer output first (how many significant points an episode really has). **Owner refinement 2026-10-23: a modifier held while dragging turns the automation snap on** (so nothing is crowded or surprising by default, and the number of points no longer matters much). Recommended key: Cmd/Ctrl, read live while the drag goes on (as the edge-trim modifier already is), because Alt already means "no snapping / ask about sync" on a clip move, Shift paints a range from a press on a clip, and a modifier pressed after the drag has started cannot trigger a press-time action (Cmd+click = add to selection). While held, the targets are the clip edges, playhead and marks PLUS the track automation points, clip envelope points and closed-stretch edges, with the dots drawn and the snap line shown; released, they go away again. **Built 2026-10-23, not seen on screen** (`ui/automation-snap.js`, `startClip`/`updateClip` in `ui/timeline.js`): Cmd/Ctrl held during a clip move adds the targets and draws the marks; the 3 dB threshold is a guess to tune on a real ducked episode. Not done: the same for edge trims and for the clipboard drag.
- **Recording: pre-upload while recording** (owner idea 2026-10-23, not started, not planned in detail; live transcripts were deferred on 2026-10-23; reopened as a separate one-track feasibility proposal on 2026-10-27, below): the finished pieces of a take go to Colab (or Drive) while the take records, so the upload is mostly done when Stop is pressed and the one transcription run starts at once; the transcript still arrives after the take. A failed or slow upload never touches the recorder (ground rule 17) and falls back to uploading after Stop. Needs: a prior-art look, the recorder's segment boundaries (the take is written as numbered segments with timings; their length is unchecked), a `colab-transcribe` that accepts files that already sit on Drive/in the session (a podcast-side wish), and the privacy note (audio leaves the Mac, via Drive unless `no_drive`).
- **Live local Orukeet while recording — feasibility reopened (owner 2026-10-27; not built).** Start with one selected track and a persistent shared-podcast worker that keeps the model warm. Transcribe short overlapping chunks from captured audio outside the recorder callback, append stable word times on the recording clock, and reconcile boundary words. Measure sustained processing/audio ratio, latency/backlog, memory and actual recording dropouts before admitting more tracks. The MLX backend uses Metal/GPU as well as CPU resources, so CPU core count minus two/three is not a capacity estimate. Use bounded queues and adaptive admission; ASR may lag or pause, while audio capture always continues. Keep provisional live words distinct from a final post-record pass. This is research for a later release, not part of the v26.10.27.4 combined recording, certificate and toolbar release.
- **Recording from several devices** (owner 2026-10-23): let the OS do it. A macOS aggregate device (Audio MIDI Setup > Create Aggregate Device, with Drift Correction on for the devices that are not the clock) shows as ONE device with all the channels, which the multi-channel recording (WP12b) already handles. Nothing to build; to do: say so in the Recording help, and check on a real aggregate device that it is listed with every channel and that the take stays in sync (not tried: the dev Mac has no input device).
- **Merged 2026-10-25 from Codex (C7, C8; not seen on screen, not tried with a microphone): cart clips trimmed on early stop and level-matched to the voices (with a manual trim); the automation snap (Cmd/Ctrl) for edge trims and clipboard drops. Still open for the cart: keeping the cart track if the editor window is closed and reopened mid-take, and the live check that a preview and a take run together on one audio device.**
- **Recording (built 2026-10-25, not seen on screen, not tried with a microphone): the slim recording bar (Stop and Add marker beside the chip) and "Play the other tracks while recording" with a manual recording delay (cut from the take's head). Open: measuring the delay (tap-to-click), a visible "editing paused" state, stopping the monitor if the recorder dies by itself. Settings in a native Kuulas app menu: decided not to build blind (pywebview gives no hook for the app menu; it needs PyObjC on the main thread and cannot be tried without a window); Preferences stays in File and on Cmd+Comma.**
- **Muted clip vs silenced stretch (built 2026-10-24, not seen on screen):** a muted clip shows a crossed-out speaker after its name; M on a silenced stretch selects the clip it opens. Level blocks is now a non-modal side panel (built 2026-10-24, not seen on screen): stale after an edit, Apply off until Measure again.
- **Menu structure for first-time users** (owner 2026-10-24: the menus are unwieldy; Opus design review in docs/design/MENUS.md; **built:** the Cart moved to Playback (it was two submenus deep, where the bar cannot open it), a test that no submenu holds a submenu, and the menu flash on a key chord; **built 2026-10-24 after the owner answered yes to all seven (not seen on screen):** File (Versions, More exports), Track (Role, Bus), Text (Placeholders), Playback (one Speed submenu), View (Options, History out of Go), Help > Getting started. **Open:** question 6, Settings in a native Kuulas app menu (the native bar only keeps what pywebview gives; Preferences stays in File until checked).
- **Picture lock / editing rounds and what happens to music cues** (owner idea 2026-10-21, to discuss tonight; belongs to versions, WP21; not started): file/version statuses (e.g. draft, in review, rendered, ready, comments to look at) and a "lock" in the film sense: the speech edit (the cut points, so the timeline duration) is frozen, but music, effects and levels stay editable. Questions to settle before building: (1) what exactly is locked (speech clips and their positions? the speech bus only? the total duration?) and what stays free (music bus, gains, automation, new tracks); (2) the real problem is the round-trip: edit, then preliminary music work, then the speech edit is revised (a cut changes): what happens to music cues? Options: cues anchored to speech (to a clip/word, so they move with it), cues anchored to absolute time (they drift), cues shown as "needs re-check" after any ripple under them; (3) is the lock a hard block or a warning ("unlock to cut")? How is an unlock + re-edit shown to the music editor (a diff of what moved: the WP21 compare of two edits can drive it)? (4) status vocabulary, who sets it (single owner here, but comments/review states may matter later); (5) is it a feature of a version (edit) or of the project. **Idea 2026-10-23 (owner, not a decision; the note was cut off, so the rest is unknown):** film does this with a change list and a conform: the editor sends not the whole project but a list of changes ("removed 12.3-15.9 s", "added here"); the sound side applies the list to its own session and the music moves along. In kuulas that would be an exported change list from the compare of two versions (WP21/WP45) that a copy of the project applies. Prior-art search (OTIO, EDL/AAF conform tools) is still to do before any design. Related: Put back and ripple all tracks (cues are split/moved with the ripple), Compare (WP45), versions (WP21).
- **Keyboard shortcut review** (owner 2026-10-21, "at some point"; not started): go through every default key. Goals: Hindenburg-compatible where it matters AND logical on its own terms (owner: wants both). Principle already agreed: frequency decides, so things used many times a session get the plain key (F Fit selection, Z zoom, E group editing, M mute) and rarely toggled modes get a modifier (Shift+F focus, Shift+P follow, Shift+S solo, Cmd+U loop); no key may need AltGr or Shift+digit, `[ ] / = \` are unusable on the Finnish layout. Decided: the Cmd+E family are the export keys: Cmd+E export mix, Shift+Cmd+E automixer export, Alt+Cmd+E mix with options; the all-tracks exports have no key. Decided 2026-10-21: A (was E) toggles range operations between all tracks and selected tracks (A for All); E is free. Plan: generate an audit table from `ui/keymap-default.js` (command, key, Hindenburg equivalent, how often the owner uses it, collisions, Finnish-keyboard check), the owner marks changes in one sitting, then one change set with tests and `docs/KEYS.md` regenerated.
- **Transcript shows only what is heard** (**hiding built 2026-10-22, not seen on screen**: `Session.heard_words`, `/api/words` carries `transcribed`, `cut_words` counts heard words, strikethrough removed; **find bar list built 2026-10-22, not seen in a window** (`material_search.py`, `/api/material-search`, `ui/material-hits.js`, Text > Find in removed material, Shift+Mod+F; try it on any project with a transcript where some word is cut or muted); **Put back built 2026-10-22, not seen in a window** (`put_back.py`: `locate`, `plan`, `apply`, `choose_range`; `POST /api/put-back/plan`, command `put_back`; ripple insert at the seam on the scope tracks, sentence by default, playhead fallback; the preview is an inline block under the hit); still open: the reading pane where you select exactly which words come back with the mouse (today: the hit's sentence), Tab to widen the range, ghost blocks on the timeline, arrows stepping through removed hits and the "Include removed material" toggle, preview ▶ and To clipboard, FILL/HOLE untried in the UI, `take_restore` to use `locate()`, clipboard filter by words, History "show the step that removed it", subtitles/transcript export still include muted words; owner decisions 2026-10-21; Opus note scratchpad/transcript-ux.md; not started): muted, soft-cut (Backspace) and Auto-Silence-closed words are NOT shown in the Transcript at all (no strikethrough, **no marker**: the transcript is for cutting existing material, not for digging up the old). Search (Cmd+F) still covers all material but never moves the playhead into removed material: the counter reads "1 of 3 in the edit · +3 removed"; arrows/Enter step only through the edit's hits; a toggle "Include removed material" (in a menu, no AltGr/Shift+digit key) makes the arrows go on through the removed ones after the edit's (MUTED/GATED hits are on the timeline so the playhead may go there; CUT/UNUSED hits are not, so a preview strip under the find bar shows the sentence in context with ▶ and Put back). Hits outside the edit appear under "Not in this edit" with a reason tag (CUT, MUTED, GATED, UNUSED) and Show / Put back (owner 2026-10-21: NOT a new track, which is the most confusing; Put back is a ripple insert on ALL tracks at the seam, music and other non-group tracks too (split at the seam, the later part moves with it: owner: losing sync is the biggest sin; re-timing a music cue is part of editing), located on the recording clock; note scratchpad/put-back-ux.md: `put_back.locate()` with kinds FILL/HOLE/SEAM/EDGE/AMBIGUOUS/NONE, WHAT comes back is what the owner selects (owner 2026-10-21): the hit opens in a read-only reading pane under the find bar showing the removed material around it (transcript style); the owner selects words with the mouse (drag, Shift+click; keyboard Shift+arrows optional) and Put back restores exactly that selection, snapped to word edges; with no selection it falls back to the hit's sentence; preview with ghost blocks and "pushes everything after X later by N s", fallback ripple at the playhead, one history step; `take_restore` to use `locate()` too). Build order in the note (coverage lookup per media, search over all material, hide words, find-bar group, put back, clipboard filter, History step). Starts after the History work merges.
- **History: show restores, undone and left-behind steps, readable names** (owner decisions 2026-10-21: collapsed by default, bracket from restore row to its target, undo/redo groups included, newest on top; design in the Opus note, sketches in the artifact "History Restore Sketches"; starts after the saved-versions work merges): (1) server lineage: a restore step's effective parent is its target, `rolled_back` / `rolled_back_by` / `restore_target` in `/api/history`; (2) dimmed rolled-back run as one collapsed row "Rolled back N steps" (icon + word, `--text-tertiary`, never opacity or strikethrough); (3) restore row "Restored to: <target>" with the "restore point" tag and a margin bracket; (4) "Undone N" (redo side, expanded) and "Left behind N" (collapsed) groups; (5) readable step names from op + arguments with a coverage test (no raw ids like set_track; en+fi); (6) collapse runs of identical steps on one object for display; (7) saved-versions filter shows where each version stands; (8) fix ui/help history.md. Keys: Right/Left expand/collapse, Enter restores, G goes to the restore point; commands in a menu.
- **Ship the automixer in the dmg** (built v26.10.20.39 branch merged, CI dmg build and a real mix with the bundled automixer NOT yet tried; licence decided 2026-10-21: Kuulas is GPL-3.0-or-later (LICENSE added, notice reworded); still open: release notes should name the podcast commit used (GPL source offer); podcast wishes in docs/PODCAST-MAGIC.md "Automixer in the dmg"; original note: today the dmg has NO automixer. Kuulas runs `uv run automixer` in a podcast checkout (`DEFAULT_COMMAND`/`DEFAULT_CWD` in automix.py) or over ssh on another Mac, so a new user who downloads the dmg cannot automix. Plan: package `apps/automixer` like speechmix, nhsx and silencelearn (path source + wheel in `build_wheels.sh`, stage script, in-dmg selftest) and run it with the app's own Python (`python -m automixer`, no uv, no checkout) when no command is configured; the folder (stems) route needs no mlx. Needs from the podcast side: a `python -m automixer` entry (`__main__`) and a wheel that builds from a clean checkout. Check first: licences of what gets bundled (pedalboard is GPL-3), wheel size, and that the external plug-ins the automixer can load (VST3/AU such as dxRevive) stay optional and are found on the user's Mac; a first-run message when a plug-in is missing. Settings > Automixer keeps "command" and "remote" overrides for the owner.
- **Learn Auto-Silence values from your own muting** (built v26.10.20.38 on the shared silencelearn package, only Sensitivity, untried on a real recording; podcast-side wishes in docs/PODCAST-MAGIC.md; original idea: needs design + prior-art check done below): mute some clips by hand (the stretches you consider silence), select a set of clips containing both muted and unmuted ones, run "Calculate Auto-Silence values from the selection": the muted clips are the examples of "closed", the unmuted ones of "open", and the result (sensitivity/margin, closeness, minimum closed time, leak between tracks) fills the Auto-Silence panel (live preview then shows what it would close; Accept as today). Prior art: the podcast repo has `packages/silencelearn` (extracted from podcast-magic `silence/calibrate.py`, shared with colab-transcribe: threshold from the muted stretches of the first minutes, leak from other tracks, speech guard, muted-block merging with `BLOCK_GAP`, `MIN_SECONDS`). Not on the podcast main yet (it lives on a worktree branch, "Unreleased"). **Decided (owner, 2026-10-21): no duplicated code.** Kuulas depends on the shared `silencelearn` package like it does on `speechmix` and `nhsx` (path sources in pyproject today). Improvements go into the package so podcast-magic, colab-transcribe and Kuulas all get them. To do: (1) podcast session lands `packages/silencelearn` on the podcast main (it is on a worktree branch, "Unreleased") and makes it take plain regions + level windows, not only Hindenburg sessions; (2) add the selection-based labelling (muted vs unmuted clips as examples of closed/open) to the package, not to Kuulas; (3) Kuulas adds the dependency and a thin adapter from its clips/tracks to the package's `Region`/`Track` types, plus the command and panel wiring. The dmg build must still resolve it (the same way as speechmix/nhsx). Series can then store the learned values (series settings already carry the Auto-Silence options).
- **Focus mode follow-ups** (v26.10.20.37): the focused track's automation band drawn tall under its waveform is not built; v2 ideas (focus history, focus follows whoever is talking) parked; owner may prefer plain F (then Fit selection needs another key). `check_docs.py` warns WP19, WP33, WP67, WP85 are in PLAN.md but not in ROADMAP.md (older, not from focus).
- **Owner priorities 2026-10-21 (evening)**: (1) **Keep-level Δ** (done both sides v26.10.20.38; untried with the real automixer); (2) **Clipboard shelves** (project / series / all; series music becomes the series shelf): Opus agent in flight, design note docs/design/CLIPBOARD-SHELVES.md first. Done today: relink keeps transcript, Mic kept open row, focus mode (Shift+F), series, silence visuals, FLAC default. Other podcast requests confirmed in docs/PODCAST-MAGIC.md.
- **Series follow-ups** (v26.10.20.36, from the builder): outros are placed where they sat, not anchored to the end of the new programme; series music can only be added to (no remove/reorder); bed level, speaker balance cap and export presets are not in the series yet; no version history of a series, no series folder that travels with a shared project (WP38); the status chip does not say which tracks differ and Apply cannot apply one section alone. UI never seen on screen.
- **Relink follow-ups** (v26.10.20.35): the relinked file has no transcript (words are keyed by media), the old media still shows as missing in File > Locate media; waveform layer looked ~9 % stretched in a headless screenshot (unchecked), outline-mode performance on a 45-min view unmeasured.
- **Clipboard scopes** (built v26.10.20.38, UI not seen; design in docs/design/CLIPBOARD-SHELVES.md; drag from the panel to the timeline done; remaining: dragging a single clip out of a multi-clip entry; original idea:): the clipboard gets three shelves: *this
  project* (today), *shared within the series* (intro/outro/jingles/ads used by every episode of the series) and
  *shared with all* (every project, e.g. a station ident). Entries stay references to media (rule 17: no copies lost,
  hash-checked). Copy/Cut go to the project shelf; "Move to series shelf" / "Move to shared shelf" promote an entry;
  the Clipboard panel shows the shelves as sections, paste forms work from any. This replaces the "place series music"
  command's own storage in the first Series version (series music = the series shelf). Needs a design note after Series lands.
- **Series: shared settings across episodes** (owner request 2026-10-21, QoL, not started, needs a design note first):
  a series is recorded in the same place, so the de-bleed values and Auto-Silence values found for one episode
  should carry to the next. Not a global preference (other series sound different) and not per episode only: a
  new level, the **series**, between the two. Idea: a `Series` record (name, id, settings: de-bleed, Auto-Silence
  options, bed level, speaker balance cap, perhaps track names/roles/bus layout and export presets) stored once
  outside the project (a series folder or a library file), and a project points to it by id. New episode from a
  series starts with its settings; "Save as series defaults" copies the current values up; a project can override
  and shows that it differs. Open: where a series lives (next to the projects, or `~/Library`), how it travels with a
  shared project, what happens when the series file is missing (project keeps its own copy), versioning of the
  settings. Search prior art first (DAW templates, Hindenburg/Reaper project templates).
- **Implicit marker at the last cut** (owner request 2026-10-20, QoL, not started): after a cut, the splice point is
  remembered as a hidden "ghost" marker (not drawn, no visible in/out). If the user then sets only an OUT marker later
  in time, the IN marker is placed at the splice, so the range extends from the cut just made (extend a cut forward).
  If the user jumps before the splice and sets only an IN marker, the OUT marker is placed at the splice (extend
  backwards). A marker is a guess only while its partner is unset; setting both explicitly overrides the guess; clear
  marks (Shift+Alt+I) forgets the ghost; a new cut moves it. Undo/redo restore it. Pure logic first (state + tests).
- **Volume envelope points by double-click** (owner request 2026-10-20, QoL, not started): double-click on a clip's gain
  line (or the envelope) adds a control point at that frame; double-click on an existing point removes it; drag moves it
  (as now). Replaces the Alt+click spec in docs/PLAN.md (Alt+click can stay as an alias). Only near the line, so other
  double-clicks (rename, open) are unaffected. One undo step each, `set_clip_envelope` with coalescing for drags.
- **Drag clips from the Clipboard panel onto the timeline** (owner request 2026-10-20, not started): drag a clipboard
  entry (or a single clip of it) from the Clipboard tab into the timeline; while dragging show the clip outline(s) as a
  ghost at the drop position and track (snap as for moving clips, Alt stops at neighbours, overwrite rules as paste),
  highlight the target track, Esc cancels; drop = the same paste op as Cmd+V at that frame and track (one undo step).
  Multi-clip entries keep their relative layout. Builds on the paste target-track fix (branch paste-target-track).
- **Looping clips (music beds)** (owner request 2026-10-20, like GarageBand, not started; M3+): two steps. (1) **Loop the
  whole clip:** a clip gets a loop switch and can be dragged/extended past its source end, repeating the source
  seamlessly (sample-accurate wrap, optional short crossfade at the seam; the source is never modified, the clip stays a
  window on media; fades and gain apply to the whole looped clip). (2) **Loop a section (the clever version):** in/out
  points INSIDE the clip's source mark the loop region: intro (unlooped) + loop region repeated N times (or until the clip's
  end is dragged out) + outro (unlooped, the rest of the source after the loop region); the outro always plays last, so
  the bed can be stretched to any length. UI: loop handles on the clip, clip shows repeat ticks; ops `set_clip_loop`
  (region + count/length), engine reads wrap around the region; export/stems render it identically; undo as one step.
  Open question: how it interacts with sync/groups, ripple trims and the fade-out (suggest: fades at the clip ends only).
- **Auto-mix inside Kuulas** (owner request 2026-10-20; the mixing becomes editable clips/levels/automation in the GUI,
  and the export tells the automixer what is already done). Phase 1 (building): **Set music level**, a Track > Auto
  command that measures the speech and the music beds (same rule as the automixer: the loudest 3 s moment of the music
  vs the speech level while someone speaks) and sets the music track/clip gain to a chosen distance under the speech
  (default -10 dB, editable; the automixer's own fixed rule is -1 dB), one undo step. Phase 2: **Level blocks**
  (speechmix block gains written as clip gains, splitting clips where needed). Phase 3: **'Done in Kuulas' manifest** in
  tracks.json (applied: block_level, bed_level_db, music_duck, mic_gates) so the export adds `--no-block-level`,
  `--no-music-duck` and tells the automixer to keep the stem level for beds; the automix dialog shows a 'Done in Kuulas'
  badge next to those options. Needs from the podcast repo: `--bed-under-speech-db` (requested in PODCAST-MAGIC.md) and a
  'keep the stem level for beds' switch. DSP (debleed, de-smack, EQ, compressors) stays in the automixer.
- **Duck under speech as a track property** (owner decision 20.10.2026; design and the migration path to clip-level
  ducking in docs/design/DUCKING.md): `Track.duck` (default: music ducks), one command Track > Auto > "Duck music"
  writes it as editable track automation, export passes `--no-music-duck` (Done in Kuulas). Not started; after Level
  blocks and bus roles are merged (same files). Open: should the automixer stems carry track gain (today dry).
- **Bounded speaker balance** (owner decision 20.10.2026, values are a starting guess to tune by ear): the automixer
  measures each speaker after the user's own gains and corrects at most `--balance-speakers-max-db` (requested from
  the podcast session, docs/PODCAST-MAGIC.md "Speaker balance"). Kuulas sends 6 dB when nothing was adjusted by hand
  and 2-3 dB when something was; "Keep my levels" sends 0. "Adjusted by hand" = any speech track gain or clip gain
  (or envelope) that is not zero; v1 does not tell Match loudness or Level blocks results apart from hand edits (they
  count as hand edits too; refine later with provenance). Dialog: one choice "How much may the automixer adjust
  levels" (Automatic / Fine-tune / Keep my levels), default by that rule. Waiting on the podcast flag; then build,
  gated like `--bed-under-speech-db`.
- **Focus mode and lane sizes** (owner decision 21.10.2026, design review in docs/design/FOCUS-MODE.md): E does NOT resize lanes; with the scope narrowed the in/out band and bars are drawn only on the lanes in scope (done, v26.10.20.22). F (WP28, `ui/focus-layout.js`, written but not wired) gets the whole show: the focused lane grows, the others shrink or become strips, animated (120 ms, not while playing, respects reduced motion). Not started.
- **Smaller project folders** (owner data 2026-10-20: 1.1 GB = backups 862 MB, caches 139 MB, history 112 MB, media 7 MB,
  recordings 0): compressed and size-capped backups plus a size breakdown in Statistics (building).
- **History panel page on a restored edit is O(n)** (found 2026-10-22, CI red on `test_sides_of_some_steps_agree_with_the_whole_map`): the page's fast path knew only past/redo/branch, so after a Restore it mislabelled `rolled_back`. Fixed by using the full lineage for any edit that holds a restore step; edits without one keep the flat fast path. Open: keep the rolled-back set incrementally like `_past`, so a long restored history is also flat (budget: 50 ms per edit at 50 000 steps). Flaky under load, pass alone: `test_colab_session` cancel, `test_colab_transcribe` cancel, `test_engine_stretch` block cost.
- **History compaction: PARKED, findings recorded** (owner 2026-10-20: nothing to do yet). What we know: the history
  database stores the whole state per node (112 MB after about two days of work on a 47-minute, 5-track project), and every
  automatic backup is a full copy of it, so history size multiplies through the backups (fixed separately by compressing and
  capping backups). Compaction would mean: drop history nodes older than a named/complete version, keep named versions and
  the current state, then garbage-collect media that no kept node references. Order matters: prune the history FIRST
  (so no kept node points at removed media), then look at media. Rules to keep when it is built: (1) recorded takes inside
  the package are the only copies (rule 17): archive them (move to an archive folder or zip next to the project) and delete
  only after an explicit 'delete permanently (X GB)' confirmation; the Recordings list (WP12e) is the way back; (2) media
  that is only LINKED from outside the package (imports by link, Dropbox folders) is not ours to delete or garbage-collect,
  and Kuulas cannot know when someone else deletes, moves or renames it: such files can vanish without Kuulas noticing, so
  the open path must keep detecting missing/changed linked media (hash check, relink dialog, clear 'missing' state on clips)
  and compaction must never assume a linked original still exists when deciding that something is safe to drop; (3) make a
  backup copy of the database before compacting; (4) the trigger is an offer when a version is marked complete (WP64),
  a manual command, and a warning above a size threshold (e.g. 2 GB), never silent. Open decisions: archive vs delete default
  for unreferenced recorded takes, and whether to store state diffs instead of whole states (would shrink the database
  itself, larger change to the history model, see WP40 'long history stays fast').
- **Quick mute for lip smacks** (owner request 2026-10-20, QoL, not started): two forms, both one key. (1) "Mute
  from mark to cursor": set a mark, play on, press the key, and the stretch mark..cursor is muted (a soft cut, hatched).
  (2) "Mute around cursor": one key mutes a fixed short stretch centred on the cursor (default 0.5 s, so 0.25 s before and
  after; length a setting). Both split the clip(s) at the edges and set `muted`, as one undo step; scope follows the
  track/range rules (WP83). Key: not on AltGr or Shift+digit, N stays free; menu entry in Clip (menu-coverage test).

- **A packaged app** (WP55, owner request 2026-10-18, milestone M2): CI builds a macOS app on tags, then
  Windows and Linux, then signing; needs speechmix and nhsx published as packages first.
- **Selection that serves double duty** (WP54, owner request 2026-10-18): convert between clip selection, range and
  words (select range on all tracks, clips touched by a range, everything from here forward, Mod+click).
- **Scriptability** (WP53, late, owner request 2026-10-18): every GUI action a documented command, a command
  catalogue, headless use, a tested "remove the ums" example; MCP and a script runner later.
- **Drag a range to edit it** (WP6, owner request 2026-10-18): press-drag-release in the lanes
  selects a range for X / Backspace; clips move by their label strip.
- **Display scale, zoom by dragging, remote control** (WP52, owner requests 2026-10-18): normalised
  waveform display, drag a range on the ruler to zoom, `kuulas ctl` to drive a running window.
- **Status tracking** (WP51, owner request 2026-10-18): Draft, Ready for review, In review, Needs
  fixes, Reviewed, Approved, Published as editable defaults; per edit, with history.
- **Mobile listen-and-comment PWA** (owner request 2026-10-18, put last): a listening copy,
  a read-only PWA with play/skip and comments by dictation, comments imported as markers.
- **Loop playback** (WP50, owner request 2026-10-18): loop the in/out range, selection or
  clip; engine wrap with the skip crossfade, toggle on Mod+L.
- **Loudness monitoring with a target LUFS per track** (WP49, owner request 2026-10-18): the
  levels drawn from analysis against each track's target, not live meters (speechmix mixes offline).
- Colab transcription: `colab-transcribe` only takes `.nhsx` sessions today.
  Recommended next step: add a plain-audio mode in the podcast repo
  (`--audio <file> --json <out>`) and import its word JSON with
  `transcribe.parse`. Do not send private audio through Google Drive; kuulas
  should invoke the VM directly. This needs a separate user decision before
  implementation.
- speechmix chain per track (leveler, de-ess, compressor, dxRevive) rendered to
  processed media, toggleable per clip.
- Export with mastering (`speechmix.programme.master`, target LUFS), rendered
  in parallel blocks.
- Hindenburg `.nhsx` import via `nhsx`.
- Video files with several audio streams: choose the stream (today: first).
- Desktop wrapper (pywebview or Tauri) so it is an app, not a browser tab.

## Milestones

Grouped from the build order in `docs/PLAN.md` (Triage) and updated by the owner's decisions. Status snapshot reviewed 2026-10-30 against `main` at `b784259`; M1/M2 counts still include owner confirmation items. ✓ done (built and merged; owner testing is tracked in `docs/BUGS.md`), ◐ partly done, ▶ being built now, ↻ built and in review (not merged yet), otherwise open. Mirrors the roadmap page.

**M1 · First playable build** (23 of 28 done, 5 partly): Run kuulas, import, listen, edit by keyboard, undo, export WAV or MP3.

✓ WP0, ✓ WP24.1, ✓ WP33a, ✓ WP29, ✓ WP30, ✓ WP1, ✓ WP34, ✓ WP36, ✓ WP2, ✓ WP3, ✓ WP33b, ◐ WP4, ◐ WP5, ◐ WP19a, ✓ WP35, ✓ WP11, ✓ WP15, ◐ WP46, ✓ WP19i, ◐ WP6, ✓ WP54, ✓ WP72, ✓ WP73, ✓ WP74, ✓ WP75, ✓ WP76, ✓ WP81, ✓ WP71.

**M2 · A usable editor** (7 of 21 done, 13 partly): Transcript, mouse editing, history panel, fast listening, FX layers. What to try: `docs/M2-VERIFY.md` (M1: `docs/M1-VERIFY.md`).

✓ WP41, ◐ WP8, ◐ WP22, ◐ WP26, ✓ WP9, ◐ WP7, ◐ WP23a, ◐ WP44, ◐ WP48, ◐ WP49, ✓ WP50, ◐ WP52, ◐ WP55, ✓ WP57, ◐ WP63, WP62, ✓ WP69, ✓ WP70, ◐ WP77, ◐ WP78, ✓ WP79.

**M3 · The editing loop** (3 of 25 done, 11 partly): What makes it better than Hindenburg: cut candidates, versions, review, paste, roles, takes.

WP28, ◐ WP43, ◐ WP18, ◐ WP19f, ◐ WP24.2, WP21, ◐ WP40, ◐ WP31, WP32, WP20, ✓ WP39, ✓ WP37, ◐ WP19c, WP19d, WP19b, ◐ WP19h, ◐ WP19g, WP19e, WP45, ◐ WP51, WP60, ✓ WP65, WP80, WP64, ◐ WP82.

**M4 · Pipeline depth** (2 of 6 done, 2 partly): Voice chain, music report, Hindenburg import, rendered FX.

✓ WP14, WP10, ◐ WP25, ✓ WP13, WP23b, ◐ WP68.

**M5 · Recording and alignment** (3 of 10 done, 2 partly): Foolproof recording, clip bin, align by sound.

◐ WP12, ◐ WP17, WP16, ✓ WP12a, ✓ WP12b, ✓ WP12c, WP59, WP12d, WP12e, WP12f.

**M6 · Late** (0 of 9 done, 0 partly): Settings and rate change, series features, desktop app.

WP27, WP38, WP42, WP47, WP53, WP58, WP61, WP66, WP56.

## Done in this release (v26.10.16.1)

- WP0: baseline, lint clean, Biome config, README, CHANGELOG, CLAUDE.md. 87 tests pass.
- WP24.1: solo overrides mute; solo is exclusive by default. 92 tests pass.
- WP14: speech analysis runs one track per core, same result. 94 tests pass.
- WP29 (v26.10.16.5): project format v1, `Name.kuulas` package per
  docs/FORMAT.md. 135 tests pass.
- WP30 (v26.10.16.6): recording clock in flicks (words, BWF times, sync
  origins); sync groups per media, in material. 155 tests pass.
- WP1 (v26.10.16.7): `Session`, one open project (edit, command, undo/redo/goto,
  import with default sync groups, transcripts, subscribe); solo/mute clicks
  coalesce (WP24.1). Not yet used by anything: HTTP API is WP3. 200 tests pass.
- WP2 (v26.10.16.8): playback engine (`engine.py`): sounddevice stream,
  1024-frame buffer, play/stop/seek/until/scrub/levels, position as heard
  (output latency subtracted), prefetch, golden renders (`tests/golden/`),
  and fault handling: failing blocks play silence and are reported, a dead
  or stalled stream is reopened on the current default device, late blocks
  raise the buffer to 2048 and say so, resampled output when the device
  refuses the project rate, damaged media chunks play silence and are
  marked. 237 tests pass. **Not yet verified on hardware:** run
  `uv run pytest -q tests/hardware/test_play.py -s` on the Mac and on
  Windows. Left open: following a default-output switch while the old
  device still works, the "rebuild damaged media" action, freezing a
  real-time layer when late (WP23a), prefetch priority over jobs (WP9).
- WP34: import survives bad files, full disks and vanished drives; 268 tests.
- WP36: caches per recording (waveform pyramid, level envelopes, decoded states, one memory budget); playback reads never touch the database; 319 tests.
- WP3 (v26.10.16.11): HTTP API (`server.py`) and `kuulas open <folder>`
  (127.0.0.1 only, free port, opens the browser, translated placeholder page
  until WP4). Endpoints: state, edit, command, undo, redo, restore (adds a
  step), history, import and upload (per-file report), peak tiles (ETag,
  immutable, 304), words, transcript import, word correction, transport,
  and `WS /api/live` (heard position, state-changed with head id, engine
  notices, jobs placeholder). Edit round trip 14 ms median on the heavy
  hour. 360 tests pass. **Not done:** `GET /api/jobs` and `POST /api/export`
  (WP9, WP11); the UI context in `restore`'s answer (null until WP8 stores
  it); not run against a real browser or with the real engine on hardware.
- WP33b (v26.10.16.12): `ui/i18n.js` (`t`, plurals, Finnish decimal comma,
  Helsinki times with the zone, key names per platform, language switch with
  an event, no reload), `GET /api/locales/<lang>`, macOS `AppleLanguages`
  before `LANG`, UI scans (keys exist, no literal text). 25 node tests
  (`node --test ui/tests/`), 369 pytest. **Not done:** the language
  setting's screen (WP27); not run in a real browser.
- WP3: local API and `kuulas open` (edit round trip 14 ms median); WP33b: UI translations; WP41: people, interviews, who speaks. 406 Python + 25 UI tests.
- WP9, WP11, WP13, WP37, WP39 (v26.10.16.14): background jobs with local
  transcription (Colab left open); export (WAV/FLAC/MP3, selection, stems,
  mastering; API only, no dialog); Hindenburg `.nhsx` import (no export);
  usage extractor; portable projects (schema v3). 480 pytest pass. **Not done:**
  real-model transcription run, two-machine portability trial, `POST
  /api/export` and jobs from a real browser.
- WP2: playback engine with fault handling and golden renders (needs the owner's listening test on the Mac: `uv run pytest -q tests/hardware -s`).
- WP25: music report builder, CSV and HTML, tags read at import, English and Finnish; test setup made order-independent. 497 tests.
- Music report: durations round up to whole seconds (owner's decision, 2026-10-17). 499 tests.
- Music report endpoint and formula guard; delete people and interviews; rebuild damaged media; decoded audio under the memory budget; test environment fallback. 521 tests (v26.10.17.2).
- Manual transcription smoke test; `av<19` pin for the transcription extra; default-output-switch findings recorded in WP2. 521 tests (v26.10.17.3).

## Later (v2)

- **Bluetooth (output latency) compensation** (owner idea 2026-10-21, late in the roadmap): Bluetooth headphones
  delay the sound by 150-300 ms or more and often report it wrongly, so the playhead cursor, the marks placed while
  listening and the word highlight run ahead of what is heard. Plan: a "Calibrate output delay" dialog per output
  device: Kuulas plays a short series of test clicks at a steady tempo and the user taps Space in time with them (tapping
  in time with a steady beat removes most of the human reaction delay; several rounds, median, outliers dropped); the
  offset is the tap-to-click difference minus a small fixed anticipation bias, shown with a live "now play" check.
  Stored per device (name/UID, in the user settings) and applied automatically when that device is the output. First
  try what Core Audio already reports (`kAudioDevicePropertyLatency` + stream latency; the engine's `_heard_now` uses
  PortAudio's number today) and only offer the manual calibration when the reported value is suspicious or the user
  wants to correct it. Applies to the VISUALS (cursor position, marks set during playback, transcript follow), never
  to the audio or the edit data. Prior art to read first: Ableton's "Driver Error Compensation / manual output latency",
  Reaper's audio latency offset, Logic's I/O buffer test; a microphone loopback does not help with in-ear Bluetooth.
  Not started.
- **Hindenburg round trip** (export back to a Hindenburg session, `.nhsx`): punted by the owner on
  2026-10-18 ("it can happen way later"). The import stays; the fallback for now is "Export all tracks"
  (per-track WAVs, same length and start) which Hindenburg can import at time zero.
- **Full-stack playback**: hear the mixed package (effects and loudness applied) inside
  kuulas, rendered in chunks ahead of the playhead on spare cores (WP23b). Owner:
  later, not in the first version.

- **Focus history** (back to the previous focus) and **focus that follows
  whoever is talking** during playback. Parked from WP28.

- **Scrub the take while it is still recording**, to place a late-logged
  marker by ear without stopping. Parked from WP12. Feasible because takes
  are raw PCM files readable as they grow; needs a monitoring design so that
  playback is never confused with the live input.

## Open questions and known limits


- **Built, not yet seen by the owner (v26.10.19.24):** pre-roll (WP12c; real microphone untried), detached transcription (WP79; real Colab and the bundled worker untried), Locate media and Send a copy (dialogs unseen), sync confirmation dialog, top bar and transcript layout, Record button. Owner hardware test so far: unplug and replug of a USB microphone and Force Quit both left the recording intact (2026-10-19).
- **Decided 2026-10-19:** WP35's remaining parts (panel sizes and per-dialog last values) go to M2 together, as one task; WP15 is done for Mac only (Windows and signing stay open). Compare (WP45) waits for mockups. Clip-moving report (could not reproduce; needs the symptom).
- **Next:** WP12b multi-track recording, then live waveforms, then one fuzzing pass on the recorder (WP59 part).
- **Never lose a recording (owner, 2026-10-19; ground rule 17).** Undoing past a take removed its clip; the file was safe in `recordings/` but nothing offered it back. Planned: a Recordings list (File menu) of every take in the project, used or not, with one-click "add at the playhead"; history steps containing takes are not pruned; audit that no path deletes or rewrites a recorded file. Not built yet.
- **Recordings list, restore options (owner, 2026-10-19):** each take row has Restore…: *to a new track at its original position* (default: never replaces anything), to the playhead, to the original position (replaces timeline only, as an import does), or to the clipboard. Needs the take's timeline position and track stored in its `.take.json`. Not built yet.
- **Self-describing take file names (owner, 2026-10-19):** a take's file name should be findable in Finder a year later: `2026-10-15 14-32-07 vst s13e04 - Olli - Take 1.wav` (starts with local yyyy-mm-dd hh-mm-ss, then the text: project, track, take; sortable, no characters Finder or Windows dislike; `.take.json` sidecar keeps UTC and the rest). Only new takes get it; existing files are never renamed (rule 17). Builds on `take_names.file_stem`. Not built yet.
- **Search for cut passages (owner idea, 2026-10-19):** search the transcript for words, and for each hit say whether it is in the current edit; a hit no clip covers is "cut", with one click to bring it back (to a new track at its original position, as for takes, or to the playhead or clipboard) and, from History, the step that removed it. The transcript is per media and the clips are windows on media, so "is this word in the edit" needs no history walk. A text filter on the History list (step labels) comes with it. The Clipboard panel gets the same search (owner, 2026-10-19): filter the saved pieces by the words they contain, using the transcript of the media they come from. Not built yet.
- **Clipboard preview level (owner, 2026-10-19):** previewing a clipboard entry plays at about the project's own level or quieter, never louder (attenuation only, plus a safety limiter), because pasted material (e.g. -14 LUFS from YouTube) is much louder than a quietly recorded session. WP82 in `docs/PLAN.md`. Not built yet.
- **A docked toolbar for discovery (owner, 2026-10-26; WP86, `docs/design/TOOLBAR.md`):** a rail left of the tracks, ten buttons to start, icon or icon and text per user. Buttons never move unless the user moves them; the user can pin any menu command. Built 2026-10-26 (drag to reorder, count badge, search, use hint); not yet tried in a real build.
- **What an edit touches (owner, 2026-10-19; WP83):** sync is knowledge only and never moves anything; groups (Cmd+G) are what moves clips together; range operations act on a rectangle of time and tracks (keyboard default all tracks, mouse drag one lane, track headers override, a visible mode switch, unaffected tracks dimmed, the old E toggle retired). Edge drags overwrite neighbours by default (Alt stops at the neighbour). Not built yet.
- **Slow hold-to-play scrubbing (owner, 2026-10-19):** Shift+J / Shift+L play slowly (default 0.5x, backward / forward) and ONLY while the key is held; release stops at once. This is a different mechanism from the J K L shuttle (which keeps playing). Shift+J / Shift+L stop being the fast-listening speed nudges; those move to `,` (slower) and `-` (faster), `.` stays the fast-listening switch. Not built yet.
- **Standard Mac keys still missing (owner question, 2026-10-19):** Cmd+N (New project) and Cmd+O (Open project) are bound since this commit. Still missing: Cmd+W (Close project, back to the start page), Cmd+, (Settings/Preferences), an Open Recent submenu in File, Cmd+M (minimise; lost with the native Window menu; the yellow button works), Revert. Cmd+G is currently the old group-editing toggle (WP83 retires it; after that Cmd+G should become Group clips and Shift+Cmd+G Ungroup). Cmd+Q, Cmd+H and Ctrl+Cmd+F come from the native app menu.
- **Security goals and practices are written down in `docs/SECURITY.md`** (threat model, rules for contributors, what is built, the ordered review checklist); it is the brief for a second agent doing WP59.
- **Hardening started (WP59):** PR #1 (Jules) merged: the server refuses a Host header that is not loopback (DNS rebinding), `locate_media` validates its folder argument, and `tests/test_fuzz_hardening.py` fuzzes paths, payloads and ops. Added after review: an Origin check (a foreign or `null` Origin gets 403 on any request; no Origin passes). Still open in WP59: fuzzing the recorder (after multi-track is confirmed on real hardware, owner decision), the import/decoder inputs, project files and `.take.json` parsing, and a security review of the desktop bridge.
- **Flaky tests under load (2026-10-20):** `tests/test_background_transcribe.py::test_a_finished_transcript_is_added_automatically_with_a_notice` failed once in a 12-minute full run on a busy machine and passes alone (3 of 3); the recorder test `test_sigkill_of_the_whole_recorder_leaves_readable_files` did the same earlier. Both wait on timing (a watcher thread, a subprocess). The cancel tests `test_colab_session.py::test_cancel_stops_the_tool_and_stores_nothing` and `test_colab_transcribe.py::test_cancel_stops_the_process_and_removes_the_folder` failed once in a loaded full run too (pass alone, 2 of 2). To harden: wait on the event, not on sleeps. Not fixed.
- **Panel buttons (owner, 2026-10-19, after the top-bar rework merges):** at most three per panel, in the Play button's style (rounded, accent fill for the primary, outline for the rest): History Restore + Undo/Redo; Candidates Accept, Reject, Preview; Markers Add marker, previous/next drift; Clipboard Paste, Clear. Not built yet.
- **Engine, v26.10.18.21:** skip list and tape-rate playback are tested with a fake output only;
  please listen to the candidate preview (Shift+Space) and, once the JKL keys exist, to shuttle.
  The crossfade is equal-power (up to +3 dB for a few ms on steady audio across a join). Pitch-kept
  fast listening needs `pedalboard` as a new dependency and a render-ahead worker (planned).

- **Candidates panel decisions to confirm:** Enter, K and Shift+Space work only while the
  Candidates tab has focus (so K stays the shuttle stop elsewhere); from the timeline you step with
  `]` and `[` and press D, but must focus the tab for Enter or K. Say if you want Enter back in the
  timeline context. The preview is two plays with a timer (the engine has no skip list yet);
  someone must listen to it.

- **Cut candidates (WP18 backend merged, v26.10.18.16):** the panel, preview playback (the engine
  `skip`), keys (D, ] [, Enter, K) and the breath/noise kind are open. Thresholds (1.5 s pause,
  4 s repeat window) need tuning on a real interview. Candidates live in the material root, so
  with several edits "cut" means accepted in some edit (open for WP21). The format `version` should
  rise to 4 with a no-op migration (the key is additive and older readers keep it; no `min_reader`
  change): deferred, it touches `package.VERSION`, `db.SCHEMA_VERSION` and the migration table.

- **Follow-ups found in the transcript panel and import UI (no owner decision needed):** a lane drop creates new tracks
  (the backend cannot place onto an existing track yet); "One after another instead" re-uploads
  the files in the browser path and, if the re-import fails, the first import stays undone (Redo
  brings it back); the design's "speech on Voices, music on Music" bus option, the collateral
  "breathing" animation, focus-dimming of other speakers and find in the transcript are not built;
  a plain arrow in the transcript moves the play cursor too (confirm that is wanted).

- **Key conflict to decide (K):** you decided "reject candidate" moves to K, but K is
  also "stop" in the J K L shuttle (WP26). The keymap supports contexts, so K can be
  "reject" inside the candidates panel and "stop" everywhere else [recommended]; or give
  stop another key. Also open: Mod+T for import (waits for the desktop window), the
  palette's "Recent" group, and the Play button's key chip not following a remap.

- **WP44 merge thresholds need real recordings.** On the synthetic four-voice
  fixtures the starting values (open stretches under 0.4 s closed up, closed stretches
  under 0.3 s dropped) change almost nothing (speechmix's own smoothing already leaves
  no short stretches); at 1.5 s and 0.8 s, 15 to 30 percent of the ranges merge and the
  closed time moves 2 to 12 percent. The old estimate of 5,000 to 10,000 pieces an hour
  was not reproduced (about 4,700 pieces per hour on the fixture; the gate has about
  as many ranges as raw toggles but the state is about a fifth of the size). Owner:
  try Auto-Silence on a real interview and tell me whether it feels too fragmented.

- **CI and distribution:** the public podcast repository is checked out directly by
  `.github/workflows/ci.yml`; no read token is needed. For any installable app,
  speechmix and nhsx still need to be published as real packages instead of path
  dependencies on `../podcast` (see "speechmix as a package").

- **Decided by the owner, 2026-10-18 (about 10.10 Helsinki):** (A) Auto-Silence stays out of the
  Cuts list and the transcript, one summary line instead; (B) "Clean up cuts" is a palette
  command only; (C) one edit's soft cuts can be offered to other versions as quiet
  suggestions; (D) lift-cut on Alt+X, and "close gap on all tracks" moves to Alt+Mod+X
  (WP5's list must change); nested buses with `Bus.parent` (tree, depth 3, cascading gain, mute
  and solo; badges A, A1, A1a; eight bus hues), no tags. These are no longer parked; they are
  built after the density work. Still open: the designer's further questions 14 to 19 in
  `docs/design/GUI-DESIGN.md`.
- **Decided by the owner, 2026-10-18 (designer's questions 18, 19, 21, 22):** nested-bus badges
  A / A1 / A1a and no tags; help "Follow what I select" on by default; the sample project for
  onboarding is a 3-minute scripted interview recorded for kuulas (needs recording; a script is
  to be written). Question 11 (what clicking a collapsed bus selects) is open: the owner wants
  to try buses first, so a way to create and assign a bus is being built (UI).
- **Owner answers, 2026-10-18 (second card round):** tips (Q23) are **hover tips**: hovering over
  an action shows its short hint and its key, instead of a timed tip every N minutes (the
  `cmd.*.hint` strings are the text; a hover-tip system is still to be built, WP48). The
  status list for WP51 is right as listed. `speechmix.mix_blend(raw, render100, m, wet_shift=None)`
  is a **yes** for the podcast repo (the owner must tell the podcast session; this session cannot
  reach it). Q11 (what clicking a collapsed bus selects) waits until collapsing a bus exists in
  the GUI (a job is building it: chevron, double-click, right-click menu).
- **Owner on packaging, 2026-10-18:** speechmix and nhsx get published as real packages
  (not a private git dependency). Needs work in the podcast repo; `PODCAST_READ_TOKEN`
  is still needed for CI until then.
- **Decided by the owner, 2026-10-18:** J, K and L stay playback keys in every panel. In the
  Candidates tab Enter keeps a candidate and Backspace/Delete deletes it (done, v26.10.18.28).
- **Owner on menus, 2026-10-18:** menu items must be unavailable when they cannot
  apply, and every item must show its keyboard shortcut ("we must teach the users
  the shortcuts in the menu too"). pywebview's native menus cannot do this, so
  kuulas gets an in-window menu bar driven by the command registry (enabled state
  per command, current keymap including user remaps); the native menu keeps only
  the app items. First cut inside the WP5 job; the designer reviews its look.
  Also: when a modifier is held and a shortcut changes meaning (X vs Alt+X), the menu,
  the status-bar hints and the cheat sheet show the alternate while it is held, like
  macOS does with Option.
- **Owner on shortcuts, 2026-10-18:** browser-reserved or conflicting keys are fine
  as long as users can customise keyboard shortcuts: WP5 must define the keymap as
  data with a user override file and conflict detection; the remap UI (WP19d) can
  follow.

- **Owner decisions on the density rework, 2026-10-18:** "reject candidate" moves
  from Backspace to K (Backspace always means Delete); a plain click on a collapsed
  bus selects nothing, Shift+click selects the members' clips in that range; the
  inspector gets a small Track/Bus section now (gain, pan, bus, voice preset), to be
  built after the designer's current pass; F2 renames clips and tracks; clip label
  templates stay at the defaults until WP27. Not accepted: pulling focus mode (WP28)
  forward (it stays in M3); storing the double-click toggle's remembered value in the
  project (it stays UI state). Bus collapse is Alt+Mod+Left/Right (WP5 uses
  Alt+Left/Right for 10 ms steps). The designer calls the crosstalk backend function
  `transcript.cut_preview`; task G3 builds it as `collateral.cut_collateral`:
  reconcile the name when wiring.

- **Owner decisions, 2026-10-18:** Backspace is Delete (a soft cut: mutes in place,
  leaves the gap, restorable, never touches the clipboard); X is Cut (copies to the
  clipboard and ripples); an extensive clipboard with history is wanted (WP46); the
  desktop wrapper is part of the first version (WP15 moved up to M1); WP44 raises
  `min_reader`; a bus with one track merges into the track header.
- **Owner decisions, 2026-10-18 (third round):** first version = wrapper plus
  clipboard, Compare later; pywebview, not Electron; test on Mac and Windows, CI for
  all three on GitHub (Mac first if critical).
- **Owner decisions, 2026-10-18 (second round):** accepted as the designer
  recommended: Spot on Mod+J, Mod+F finds in the transcript, fade stays on G, Import
  on Mod+I now and Mod+T in the wrapper; `[` `]` by physical key on the Finnish
  keyboard; bus S solos the set and assigning a bus moves the track in the model;
  speech waveform dB-shaped and music linear; role strip off on the timeline; focus
  mode by speaker and by bus; Compare with up to four variants; the small pinch task
  (Safari and wrapper); panel arrangement as a later work package (WP47); skip
  DeepSeek. **Parked until mockups exist (owner: too complex to answer now):** the
  soft-cut details (Auto-Silence kept apart, "Clean up cuts", offering cuts to other
  versions, a lift-cut key). **New idea to design:** more than one bus, including
  nested ones (an "All speech" bus holding "Interviews" and "Narration"), useful for
  editing as well as mixing.

- **GUI design, 8 open questions for the owner** (`docs/design/GUI-DESIGN.md`,
  recommended answers in brackets): waveform scale for speech dB-shaped and
  linear for music [yes]; Spot (WP19f) moves from `=` to Mod+J [yes]; `[` `]`
  bound by physical key on the Finnish keyboard [yes]; Mod+F finds in the
  transcript, fade stays on G [yes]; import on Mod+I until the desktop app
  exists [yes]; bus S solos all its tracks as a set [yes]; assigning a bus also
  moves the track in the model [yes]; role strip off on the timeline, shown in
  the clip bin and cards [yes].
- **Soft cuts** (architect's note, owner has not decided yet): Backspace as
  "Cut, keep gap" with Mod+Backspace the only real delete; Auto-Silence pieces
  kept apart from editorial cuts (WP44 makes them a gate); "Clean up cuts" a
  palette command only; offer soft cuts to other edits as suggestions; "Put
  back" for ripple cuts from history. Bugs to fix first, each with a failing
  test: unmuting leaves 30 ms dips (derive the ramp in the mixer), trailing
  silence in export (`Project.length` must ignore muted clips), hit-testing
  must prefer the unmuted clip, `_crossfade` must skip muted sides.
- **WP44 and `min_reader`:** an old reader ignores the gate and plays the muted
  audio. Owner to decide whether `min_reader` goes up (recommended: yes).

- **Podcast-repo plans that overlap kuulas** (not built there yet):
  `podcast/docs/plans/2026-10-05-edit-diff.md` (diff of two edits) and
  `2026-10-05-rough-cut.md` (cut suggestions in the editor's own style,
  learned from past edits). When built, the rough cut should arrive in kuulas
  as WP18 cut candidates, and the diff should be one shared implementation
  with kuulas's changes view (WP31), not two. Decide which repo owns the diff
  before WP31 starts.
- **Voice presets belong in speechmix** (R38): `clean`, `room`, `remote`,
  `phone`, with an auto-suggestion from measurements, settings tuned by
  listening tests on real episodes. A change to the podcast repo, so it
  needs the owner's go-ahead there; kuulas only passes the preset name.

- **Project format, decisions for the owner** (docs/FORMAT.md, end). WP29
  was built with the recommended answers; say if any should change:
  1. package folder `Name.kuulas` (built), not one file;
  2. history retention: every step kept forever (built; about 110 MB for an
     extreme 5,000-step edit, measured), no thinning;
  3. OpenTimelineIO export for other editors: not built, later if wanted;
  4. two machines: the second machine opens read-only (built); is an
     explicit hand-over ("check out") needed too?
- **Undoing an import** (WP29): media rows are material and are not
  versioned, so undoing an import removes its clips but the media stays in
  the project, as in Hindenburg's clipboard. Say if undo should remove the
  media too.
- **Backup days** (WP29): "the last backup of each day" uses the computer's
  own time zone (Helsinki on the owner's machines); file names are UTC.

- **Music report format:** do Teosto or Gramex want a specific file layout? (WP25 ships CSV and HTML.)

- **speechmix as a package.** Path dependency on `../podcast/packages/*`.
  The podcast repo says it splits the pipeline out when a fourth consumer
  appears, and kuulas is that consumer. Until then kuulas builds only next to
  a podcast checkout.
- History stores a full state per edit (compressed). Fine for a session's
  thousands of edits; long-lived projects may want compaction.
- Playback is Python (numpy per block), about 20–45 ms of output latency. That
  is fine for playback, because the display is compensated for it. Monitoring
  while recording goes through the audio interface's direct monitoring, not
  kuulas. If real-time FX, scrubbing or recording hit the limits, the engine
  alone moves to a JUCE Python extension behind the same interface (WP2),
  checked against golden renders.
- Clock drift between recorders (a file running slow over an hour) is not
  handled; sync groups fix offsets only.

- Clip groups (group/ungroup/merge, v26.10.18.61) merged; **unverified by eye**: group badge, dragging a grouped clip. Decided (owner, 2026-10-18): merge joins touching clips only; bouncing/rendering in the editor is not needed now, it may come back with heavy effects (WP23b, tier 3 render).

- WP22 UI (track kind tags, Speaker field) and WP46 clipboard (paste forms, limit, preview, sharing between windows, paste into another project, names, filter) merged v26.10.18.62; **unverified by eye**. Open: WP46 excerpts when the original file is gone (use `excerpt_media.py`), preview without gate/automation; WP22 voice condition (Alt+Mod+J).
- WP56 (late, owner 2026-10-18): cut like a tape editor: lip smacks and fillers as candidates, breaths kept, silences trimmed around them, cut edges moved to syllable boundaries. Plan in `docs/PLAN.md`. Needs real recordings with marked examples from the owner; prior-art search first.
- Tab as three levels (owner 2026-10-18): clip borders, word to word, within a word (breaths, transients, syllables). Plan in `docs/PLAN.md` WP19i. Keys decided: Tab and Shift+Tab step, Alt+Tab (Mac) cycles the level (done; the three levels themselves are still to build); the fine level needs WP56 detection, and the word list must refresh on every edit.
- Dropbox-safe locks (per-host `locks/` files, v26.10.18.63) merged; **not tried against a real Dropbox**. Risks: all computers need this version, clocks within a few minutes, a lock arriving over 5 minutes late is ignored. Open: `min_reader` not raised.
- **Selects workflow (owner question 2026-10-18):** listen to the interview, highlight the best bits, then place or write around them. The clipboard (pinned entries) is a stopgap, not the clean model. The clean model is WP17 (clip bin), WP42 (bits and index-card view) and WP21 (several edits in one project: a "Selects" edit and a "Story" edit sharing the same material). Open: owner to decide whether to bring these forward and how a select is marked (transcript highlight, a range, a key).
- The owner's issue list is `docs/BUGS.md`: every reported issue stays there until the owner closes it.
- Fast listening, scrub fix, Left/Right fine nudge, Tab scopes (words, clip borders, sounds) with Alt+Tab, right-click menus on the timeline (v26.10.18.64): all **unverified by eye or ear**; see `docs/BUGS.md` for what waits for the owner's OK. WP56 sound scope: breaths and mouth noises still to build.
- Requested (owner 2026-10-18): WP59 hardening with fuzzing and a security review by the strongest model, after the first edits (note: the local server must check Host/Origin); WP60 smooth speaker changes with automatic crossfades (semiautomatic candidates). Plans in `docs/PLAN.md`.
- Requested (owner 2026-10-18): WP61 Quick Look, thumbnail and Spotlight support for `.kuulas` on the Mac, after the packaged app (WP55). Plan in `docs/PLAN.md`.
- Terminology pass (WP62, owner 2026-10-18): consistent editing verbs and marks vocabulary in en and fi; draft in `docs/GLOSSARY.md`, owner decides the open rows.
- Requested (owner 2026-10-18): WP63 real waveform in the drag ghost, plus smart guide lines and snapping between speakers' activity edges while moving a clip. Plan in `docs/PLAN.md`.
- Parked (owner 2026-10-19, "not now"): WP64 naming a saved version: an in-window name field on Shift+Mod+S, rename in the History panel, named versions standing out. Plan in `docs/PLAN.md`.
- Built in v26.10.19.2 (owner 2026-10-19): WP65 clipboard per project, persistent without pinning, with sharing (star) and browsing other projects' clipboards. **Not seen on screen yet**: click through the three views (This project, Shared, Other projects). Plan in `docs/PLAN.md`.
- Built in v26.10.19.2: loudness readout in track headers, live level meter with clip light, Track > Reset gains to 0 dB. Not tried with real playback.
- Open (2026-10-19): running kuulas with `uvx` from any folder works only with `--with-editable` (see README) because `ui/` is not packaged in the wheel and `speechmix`/`nhsx` are path dependencies on `../podcast`. A real install (ui in the wheel, speechmix as a package) is part of "speechmix as a package".
- Next target (owner 2026-10-19, for testers): WP73 an unsigned `.dmg` for macOS (Mac only), built with Briefcase or PyInstaller, with the `.kuulas` type and double-click opening; no Python, uv or podcast checkout needed. Plan in `docs/PLAN.md`. Signing, notarisation, Windows and auto-update are later.
- Built in v26.10.19.9 (owner 2026-10-19): WP73 unsigned `.dmg` for macOS testers (`scripts/build_dmg.sh`, `docs/TESTERS.md`). **Not opened in Finder.** Open: checksum-pin the ffmpeg download; signing and notarisation need an Apple Developer account; Windows later.
- Asked (owner 2026-10-19): share a session with another user WITHOUT the media (they already have most of it). The design exists (FORMAT.md "Hand-off copy": none / used ranges plus 2 s handles / everything; media identified by SHA-256 so the other side relinks from their own files, R49 done in the backend as WP39) but the UI is not built: a "Locate media…" dialog (point at a folder, verify by hash) and File > "Send a copy…" with the three media choices (WP32). Proposed as the next small step; the owner decides.
- Proposed, principle approved (owner 2026-10-19): WP80 "Versions of this part": pick an earlier version of any range from the history; choosing one is a new edit step, not an undo. Plan in `docs/PLAN.md`.
- Proposed (owner 2026-10-19): WP79 transcription as a detached background job that survives closing kuulas (job files in the project, a separate worker, results ingested as one undo step when the project is open or at the next open). Plan in `docs/PLAN.md`; the owner decides automatic add versus one click.
- Proposed (owner 2026-10-19): WP12d voiceover take notes: marks and notes while recording, per-take notes, notes anchored to words in a take. Plan in `docs/PLAN.md`. Also: re-sync commands ask first and say what they will move (owner rule, to the other kuulas session).
- Built in v26.10.19.22 (owner 2026-10-19): WP12a recording a single track (Transport > Record…, two-step stop, recorder process, takes land as clips). **Not tried with a real microphone.** Next: WP12b several channels, WP12c pre-roll 60 s.
- Next big push (owner 2026-10-19): recording (WP12, R22): first single-track (WP12a), then multitrack (WP12b), with the foolproof architecture already planned: a separate recorder process, raw PCM WAV flushed every few seconds, a 2 s hold to stop. Plan in `docs/PLAN.md`; decisions needed from the owner are listed in that section's first-version questions.
- Kuulas side built in v26.10.19.18, **waiting for the podcast side** (owner 2026-10-19): WP78 transcribe on Colab straight from kuulas, with no `.nhsx` involved: kuulas calls `colab-transcribe` in a plain-audio mode and imports word JSON. The kuulas side is built against a fake tool; the podcast side (a `--audio ... --json` mode, and the word-start correction from WP77) is requested from the podcast session. Plan in `docs/PLAN.md`.
- Parked (owner 2026-10-19): WP77 better word times with a forced aligner. The podcast session has a measurement (Whisper word starts are early, median 87 ms; 1 % are 1-2.5 s early) and an experimental aligner on podcast PR #59 (open), but no fix to integrate yet. Plan in `docs/PLAN.md`; waits for the owner and PR #59.
- Built in v26.10.19.17 (owner 2026-10-19): WP76 the timestamp: click copies, double click edits and jumps, typed offsets (+100 = forward 100 s, like FCP). Plan in `docs/PLAN.md`.
- Built in v26.10.19.16 (owner 2026-10-19, "very important"): WP75 a search field in the Help menu to find a command by typing (name, hint, synonyms; shows the menu path and key; Enter runs it, Alt+Enter shows it in the menu). Plan in `docs/PLAN.md`.
- Built in v26.10.19.13 (owner 2026-10-19): WP74 menu reorganisation, File > New/Open, export options dialog, Finnish terminology (väylä/ryhmä/leike). **Not seen on screen.** Auto-Silence, Duck the microphones and Transcribe the track are wired for the first time.
- Built in v26.10.19.8 (owner 2026-10-19): WP72 `Kuulas.app` launcher and the `.kuulas` file type on macOS (double-click, Open with…, Dock drop), step 1 without PyInstaller or signing. **Not tried in Finder**: build with `uv run python scripts/make_app.py` (Terminal.app, no sudo). Automixer mix now lands next to the project (setting `output_dir`).
- Built in v26.10.19.7 (owner 2026-10-19): WP71 two-finger scroll preference (zoom by default, View menu toggle) and WP70b durations per clip, track and session. **Not tried on a trackpad or seen on screen.**
- Built in v26.10.19.6 (owner 2026-10-19): WP70 session statistics (File > Statistics…, `kuulas stats`, /api/stats). **Not seen on screen yet.** Open: keep a snapshot per saved version to chart a series; whether mutes count as time cut out; no undo count (not recorded).
- Built in v26.10.19.4 (owner 2026-10-19): WP69 words drawn inside the clips on the timeline when zoomed in, as Hindenburg does (View > Words in clips). **Not seen on screen yet.** Open: speaker-change mark in the row; whether the row replaces the first words in the label at close zoom; text colour (clip label colour at 70 percent for now).
- Built in v26.10.19.3 (owner 2026-10-19): selecting words in the transcript sets the in/out marks, so the range shows on the timeline and can be fine-tuned. Not seen on screen yet. Open: whether the pop-up should then act on the fine-tuned marks instead of the words.
- Pure building blocks merged 2026-10-19, not wired to anything yet: series templates (anchor, schema, build, media match, next episode name), recent projects list, chapter list from markers, filler words, safe file names, stem names, gain suggestion and loudness number formats, ruler ticks. Agents: glm 18 of 19 first deliveries accepted, opencode 28 of 31 (agy and kimi pending). The Go quota is at STOP (7-day 91 percent): Go tasks go to agy.
- Removed in v26.10.19.2 (owner 2026-10-19): the `speech-mix` track kind; old projects open it as speech.
- Requested (owner 2026-10-19): WP66 series templates: save tracks, buses and chosen standing clips (anchored to start, end or a marker) and start new episodes from them. Plan in `docs/PLAN.md`.
- WP68 mixing with the automixer from inside kuulas (owner 2026-10-19). Step 1 built in v26.10.19.1 (File > "Mix with the automixer…", palette `export.automix`, dialog, Help topic, background job with Cancel): **not yet run against the real automixer**, only a fake script; the CLI flags in `automix.py` come from its README. Open: run it once for real; a "range only" option; resampling for projects that are not 48000 Hz (refused for now). Step 2 (in-process call without WAV files) is open and needs an importable mixing entry point in the podcast repo. Plan in `docs/PLAN.md`.

