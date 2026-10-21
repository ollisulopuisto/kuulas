# Series: settings shared by the episodes of a show

Owner request 2026-10-21 (ROADMAP "Series: shared settings across episodes"). First, small
version. Code: `src/kuulas/series_settings.py` (pure), `series_library.py` (the file),
`series_actions.py` (commands on an open project), routes `/api/series/*`; UI
`ui/series-model.js`, `ui/series-dialog.js`, `ui/episode-dialog.js`, File > Series.

## What a series is

Episodes of one show recorded in the same place. What was found for one episode is the right
start for the next. A level between the per-user preferences (other shows sound different) and
the project (per episode only).

## Prior art (searched 2026-10-21, about five minutes)

- **Reaper:** *project templates* (File > Project templates; a saved project with tracks, routing,
  FX; markers not included) and separate *track templates*. A template is copied once into a new
  project; later changes to the template never reach existing projects, and nothing says a project
  differs from its template. Podcast guides (SmartSound, Envato Tuts+) recommend one template per
  show for exactly this reason. <https://reaperaccessibility.com/wiki/Project_Templates>
- **Hindenburg:** "Properties - Default" saves a default session (one per user, not per show);
  new sessions start from it. No per-show defaults, no link.
  <https://hindenburg.com/academy/guides/guides-hindenburg-pro/>
- **Pro Tools / Logic:** session templates (one-shot copy) plus "Import Session Data" / track
  import to pull settings from another session on demand: the closest to "Apply series settings".

**Taken:** the template idea (a new episode starts from the series) and the explicit pull
(Import Session Data). **Added:** the project stays linked to its series by id, so "Save as series
defaults" can push the improved values up and the episode can say it differs. Nothing in those
tools applies settings silently, and neither does this: values change only on a command.

## Where a series lives

`<per-user config>/series/<id>.json` (`~/Library/Application Support/kuulas/series/` on the Mac;
`$KUULAS_SERIES_DIR` in tests), beside the other per-user files (`automixer.json`, the shared
`clipboard.json`). Why there and not next to the projects:

- The series is the user's, like the automixer settings it carries; the projects of one show are
  not always in one folder (the owner's projects live in several places, some in Dropbox).
- One file per series, `<uuid7>.json`, atomic writes, unknown keys kept: a sync tool can carry the
  folder later, and a conflicted copy beside a file is another name and never read.
- **The project keeps its own copy** (`Project.series`, below). A project opened on another Mac,
  or after the series file was deleted, opens and works the same; the dialog says the file is
  missing, and "Save as series defaults" writes it again under the same id. So the location is
  not load-bearing, and WP38's series folder can later hold the same file without a format change.

## The record

```json
{"format": "kuulas-series", "version": 1, "id": "<uuid7>", "name": "Vikasietotila",
 "updated_utc": "2026-10-21T10:00:00Z",
 "settings": {"layout": {...}, "auto_silence": {...}, "automix": {...}},
 "music": {"entries": [<clipboard entry>, ...]},
 "media": {"<sha256>": {"name": "intro.wav", "paths": ["/abs/intro.wav"]}}}
```

Settings, each section optional:

- `layout`: tracks in order (`name`, `kind`, `speaker`, `bus` by **name**, `gain_db`, `pan`, `mono`,
  `target_lufs`, `duck`, `follow_bus_role`) and buses (`name`, `kind`, `gain_db`, `pan`, `mute`).
- `auto_silence`: `SilenceOptions` (all seven values).
- `automix`: the automixer switches that depend on the room and the show (`AUTOMIX_KEYS`:
  `speech_debleed`, `speech_rider`, `block_level`, `speech_mic_duck`, `mic_duck_db`,
  `bed_under_speech_db`), every value spelled out (the tool default where the user set none). Not
  carried: the speaker balance cap (the project's own, from hand adjustments), plug-ins (per Mac),
  the command and remote settings.

Everything is read tolerantly: a damaged part is dropped or set to its default, never fatal.

## Where the current values come from, and where Apply puts them

| section | lives today | Apply writes |
|---|---|---|
| layout | the project (edit state) | the project, one undo step: same-named tracks/buses (trimmed, case-blind) get the values, missing ones are added at the end; nothing is removed, no clip touched |
| auto_silence | the user's view of the project (view memory, `state.autoSilence`); the page sends it | returned to the page, which sets it (remembered in the view as before) |
| automix | the per-user `automixer.json` options | merged into `automixer.json` (only these keys; command, remote, plug-ins and other switches stay) |

The project's link and copy, `Project.series = {"id", "name", "settings"}`, is edit state (absent
when empty, so old projects keep their bytes): Save, Apply, Join, Leave and Rename are each one
undo step. A new episode or a project with no remembered Auto-Silence options starts with the
copy's options (`ui/view-memory.js`).

Values learned with "Calculate Auto-Silence values from the selection" (docs/design/SILENCE-LEARN.md)
need nothing new here: Accept remembers them as the project's Auto-Silence options, so "Save as
series defaults" carries them to the next episode like hand-set ones.

**Differs** (`series_settings.differences`): a section differs when the episode's value is not the
series'. For the layout every series track and bus must be in the episode with the same values;
extra tracks in the episode (a guest) are not a difference. The status-bar chip shows
"Series: name" or "Series: name · differs" with the sections in its tooltip; it is refreshed 1.5 s
after an edit and after every series command.

## Commands (File > Series; no default keys: Finnish layout)

- **Series…**: the hub. Name / choose / join / rename / leave, the status, the music count, Save
  and Apply.
- **Save as series defaults…**: copies the episode's values up; a project in no series asks for a
  name (or joins the chosen one) and creates it.
- **Apply series settings**: pulls the values in (above). One undo step for the project part.
- **New episode from series…**: name (the next episode: last number + 1, padding kept), folder
  (beside this project), series. Makes the project with the layout and the copy, then opens it (the
  desktop window via `Bridge.open_path_in_window`, a browser via a new tab).
- **Add selected clips to series music**, **Place series music on the timeline**, **Put series
  music on the clipboard**: below.

## Series music (and the Clipboard's future series shelf)

The owner's idea: the series remembers the intro, outro and beds and puts them on the timeline of
a new episode, or on the clipboard. Simplest safe design, built now:

- An entry is a **clipboard entry** in exactly `clipboard.json`'s format (references by SHA-256,
  source windows, gains, fades, track slots and names, the source project), never audio.
- `media` maps each SHA-256 to the paths where the recording was found (`media_paths` of the
  project it was added in). Placing links a recording the episode lacks **in place** from one of
  those paths after checking its hash, else from the source project (`clipboard_link`). Nothing
  is copied, moved or written to a recorded file (ground rule 17); a recording that cannot be
  found is reported and its clips left out.
- **Place** pastes every entry where it sat in its episode (`span[0]`), on the tracks of the same
  name, overwrite mode, all in one undo step; an entry whose track the episode lacks is reported.
- **Put on the clipboard** adopts the entries into the project's clipboard (the normal paste then
  works).

**Shaped for the Clipboard scopes** (ROADMAP "Clipboard scopes", owner 2026-10-21: shelves *this
project*, *shared within the series*, *shared with all*): the series shelf is
`series/<id>.json` → `music.entries`, already in the clipboard's entry format with the media
paths beside them, so the Clipboard panel can list them as a section and "Move to series shelf"
can append to the same list. When the shelves are built, "Place series music" and "Put on the
clipboard" become paste forms of that shelf and this file's `music` stays the storage.

## Not in this round (follow-ups)

- Anchors: an outro is placed where it sat, not from the end of the new programme (WP66's
  `template_anchor` can do this; needs the programme length, which a new episode does not have).
- Removing one music entry, or reordering: today only add; the file can be edited by hand.
- Bed level, speaker balance cap and export presets in the series (ROADMAP idea list).
- Version history of a series; a series folder that travels with shared projects (WP38).
- Showing *which* tracks differ, and applying one section only.
