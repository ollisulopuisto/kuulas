# kuulas roadmap

A multitrack **editor** for spoken word: podcasts, interviews, radio. It is
for editing, not recording. The model is Hindenburg PRO: keyboard-first,
speech-aware, with the transcript and the audio as one thing.

Out of scope: loopback, publishing integrations, anything but basic recording, spectral repair/spot healing, music remix/retiming.

**How it gets built:** `docs/PLAN.md`, in work packages for implementers.

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
| R5 | Transcription, local and Colab | local (faster-whisper) and JSON import written; Colab next |
| R6 | Edit audio by editing the transcript, and vice versa | done in core: words follow clip edits; deleting words cuts all tracks at pause midpoints |
| R7 | Clip ops Hindenburg lacks: clip volume, pan, gain automation | done in core |
| R8 | Mac, Linux, Windows | by design (Python engine + browser UI); tested on Mac only |
| R9 | Never lose work; smart undo | done: every edit fsynced to SQLite, undo tree keeps branches, drags coalesce |
| R10 | **High priority.** Hindenburg-level keyboard editing; every UI feature ships with its keys | keymap taken from the Hindenburg PRO shortcut list; UI next |
| R11 | Pro Cut Auto-Silence: mute what does not cross the threshold | done in core (speechmix grid + duck masks → muted clip pieces) |
| R12 | Auto crossfade only where non-adjacent audio is joined | done |
| R13 | Media identified by content hash; survives rename/move | done (SHA-256 ids, every seen path remembered) |
| R14 | Per-source mono/stereo; measurements aware of it | done: mono voices constant-power, stereo music balanced, stereo master; speech analysis reads speech tracks only |
| R15 | Select everything from the playhead on (one track / all tracks) | done in core (`clips_from`, `clips_until`, multi-clip edits) |
| R16 | Sync groups: mark clips in sync, move freely, resync any subclip to the main clip | done in core, timestamps only; fixes accidental one-track cuts |
| R17 | Late sync: mark from clips still in sync, or from file timestamps (BWF) | done in core |
| R18 | Store media as FLAC to save space | in progress: lossless FLAC verified bit-exact for 16/24-bit PCM |
| R19 | Link media in place or copy into the project (like FCPX) | in progress: link PCM in place, relink by hash, consolidate |
| R20 | Ingest every audio format and the audio of video files | in progress: ffmpeg decoder |
| R21 | Heavy parallel processing | imports parallel; analysis, transcription, export next |
| R22 | Basic multitrack recording, standard APIs only (CoreAudio/WASAPI via PortAudio), Mac first; foolproof modal record mode: only a 2 s hold stops it, backend keeps recording if the UI closes, no sleep | planned: WP12 |
| R23 | Sync workflow: files imported or recorded together are in sync by default; align any other file by eye and mark it in sync; optional align-by-sound helper for Zoom/phone files (drift, dropouts) | core done (sync groups); default groups in WP1; helper WP16 |
| R24 | Space never plays a clip list; dropping never trims to in/out; previews loudness-matched | planned: WP17 + plan-wide rules (important, can come later) |
| R25 | Mark possible cuts on the first listen, decide on the second; markers stay on their audio through every edit | planned: WP18 |
| R26a | Edit groups: an edit applies to the whole sync group unless group editing is switched off (Pro Tools, Reaper) | planned: WP19a |
| R26b | Connected clips: music and effects stay attached to a moment in the speech through ripple cuts (FCP) | planned: WP19b |
| R26c | Roles (dialogue / music / effects), stem export per role, Match Loudness (FCP, Audition) | planned: WP19c |
| R26d | Every command bindable, user key overrides, macros that undo as one step (Reaper) | planned: WP19d |
| R26e | Alternative takes in one slot, switched with one key (Pro Tools playlists, FCP auditions) | planned: WP19e |
| R26f | Spot: type an exact time to place a clip or the playhead (Pro Tools) | planned: WP19f |
| R26g | Skimming: hover to hear without moving the playhead (FCP) | planned: WP19g |
| R26h | Markers and regions, batch export of regions, chapter list (Reaper) | planned: WP19h |
| R26i | Tab to transient or to word, cycled with one key (Pro Tools) | planned: WP19i |
| R27 | Copying clips between projects never copies whole source files: reuse by hash, link in place, or copy only the used range plus 2 s handles | planned: WP20 (must-fix) |
| R28 | Several edits (versions) of the same material in one project, e.g. 1 × 60 min and 4 × 20 min: shared media, transcripts and sync; separate cuts and undo; cut decisions offered across edits | planned: WP21 |
| R29 | **MUST.** Undo you can trust: Mod+Z stays on the current branch, history restores add a step instead of rewinding, undo brings back selection and view and shows what changed | planned: WP8 |
| R30 | **Needed.** Track tags (speech / speech-mix / music) are all speechmix needs; ducking of mics and music beds from speechmix + nhsx.musicbed; FX layers: real-time, analyse-then-live, or rendered | planned: WP22, WP23 |
| R31 | **Needed.** Solo overrides mute and is exclusive by default (mute all, solo one at a time); A/B tracks, edits, takes and layer settings with one key, level-matched by default | planned: WP24 |
| R32 | Music report per edit: every piece of music actually heard, with metadata, programme times, duration and background/featured, as CSV and printable table | planned: WP25 |
| R33 | **MUST.** Sped-up listening (toggle normal/fast, pitch kept) and JKL shuttle with slow and fast scrubbing | planned: WP26 |
| R34 | Project settings changeable later, undoably: sample rate (e.g. 44.1 → 48 kHz, every position converted), mono or stereo master, loudness target, export defaults | planned: WP27 |
| R35 | Own project format `Name.kuulas` (package folder): shared material (media, sync, transcripts) apart from per-edit state; recording facts in flicks so they survive rate changes; versioned with forward compatibility; crash-safe, locked against two writers, automatic backups; lossless Hindenburg round trip | WP29 done in v26.10.16.5 (package, manifest, lock, v1 schema, material apart from edits, UUIDv7 steps, checkpoints, backups, v0 migration, `kuulas info`); WP30 (flicks, sync per media) next; Hindenburg round trip in WP13 |
| R36 | Focus mode: F focuses a speaker's tracks, the others shrink to strips that keep sync visible; Shift+F also solos; transcript dims other speakers | planned: WP28 |
| R37 | Review round trip: A sends v1, B edits (some changes done, some as suggestions), A gets v2 and accepts or rejects each; works even if A kept editing; hand-off copies carry only used audio | designed: docs/FORMAT.md; build WP31 (changes view), WP32 |
| R38 | Voice condition as a sub-choice of speech ("Speech · remote"; also for speech mixes, never music): clean / room / remote / phone / auto picks a speechmix preset; auto-suggested from measured noise floor, bandwidth, echo and clipping | waits for presets in speechmix (podcast repo); kuulas side in WP22 |
| R39 | Internationalisation from day one: English and Finnish complete, one catalog for Python and UI, speechmix's messages translated too; locale-aware numbers, Helsinki times with zone, platform key names | WP33a done in v26.10.16.4 (Python catalogs, `messages.t`, speechmix translator); WP33b (UI) open |

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

## In flight

- Media store: linked vs working FLAC, ffmpeg for everything else, relink,
  consolidate.
- Playback engine (sounddevice), HTTP API, browser UI with the keymap.

## Next

- Colab transcription: `colab-transcribe` only takes `.nhsx` sessions today.
  It needs a plain-audio mode in the podcast repo, or kuulas writes a
  minimal `.nhsx` for it.
- speechmix chain per track (leveler, de-ess, compressor, dxRevive) rendered to
  processed media, toggleable per clip.
- Export with mastering (`speechmix.programme.master`, target LUFS), rendered
  in parallel blocks.
- Hindenburg `.nhsx` import via `nhsx`.
- Video files with several audio streams: choose the stream (today: first).
- Desktop wrapper (pywebview or Tauri) so it is an app, not a browser tab.

## Done in this release (v26.10.16.1)

- WP0: baseline, lint clean, Biome config, README, CHANGELOG, CLAUDE.md. 87 tests pass.
- WP24.1: solo overrides mute; solo is exclusive by default. 92 tests pass.
- WP14: speech analysis runs one track per core, same result. 94 tests pass.
- WP29 (v26.10.16.5): project format v1, `Name.kuulas` package per
  docs/FORMAT.md. 135 tests pass.

## Later (v2)

- **Focus history** (back to the previous focus) and **focus that follows
  whoever is talking** during playback. Parked from WP28.

- **Scrub the take while it is still recording**, to place a late-logged
  marker by ear without stopping. Parked from WP12. Feasible because takes
  are raw PCM files readable as they grow; needs a monitoring design so that
  playback is never confused with the live input.

## Open questions and known limits

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
