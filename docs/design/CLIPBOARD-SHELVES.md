# Clipboard shelves: this project, the series, all projects

Owner idea 2026-10-21 (ROADMAP "Clipboard scopes"). Builds on WP46/WP65 (the clipboard) and
the Series (docs/design/SERIES.md, v26.10.20.36). Code: `series_actions.shelf_*`, routes
`/api/series/shelf*`, `ui/clipboard-panel.js` (the Series view).

## Three shelves, three files that already exist

| shelf | what it is for | stored in | override (tests) |
|---|---|---|---|
| **This project** | every Copy and Cut (as today) | `<project>.kuulas/clipboard.json` | none (the project's folder) |
| **Series** | intro, outro, jingles, ads used by every episode of the show | the series file: `series/<id>.json` → `music.entries`, with `media` | `$KUULAS_SERIES_DIR` |
| **Shared** (all projects) | a station ident, anything any project may use | the per-user `clipboard.json` in `~/Library/Application Support/kuulas/` | `$KUULAS_CLIPBOARD_FILE` |

No new file. The series shelf **is** the series music of v26.10.20.36: same list, same format,
so "Place series music on the timeline", "Put series music on the clipboard" and "Add selected
clips to series music" keep working on the same entries. The shared shelf is WP65's shared
store; its star stays.

## Entries

Every shelf holds `clipboard.json` entries (docs/FORMAT.md): references to recordings by SHA-256
plus windows, gains, fades, layout and track names. Never audio. Nothing on any shelf ever
copies, moves, overwrites or deletes a recorded file (ground rule 17). A recording is linked
into an episode only **in place** and only after its hash was checked
(`clipboard_link.has_digest`). The series file's `media` keeps where each recording was seen
(the project's `media_paths`), added to on every put; that is how a new episode finds it.

## Moving between shelves: always a copy

- **Add to series shelf** (a project entry): a copy with the **same id** goes on the series
  shelf; the project entry stays. **Add to shared shelf** is the existing star (same id, same
  rule). The project shelf is the history of what was copied; taking an entry off it is only ever
  the user's Delete. The same id lets the panel show that an entry is on the series shelf.
- **Copy to this project** / **Paste here** on a series or shared entry: adopts a copy (new id,
  `adopted_from`) into the project shelf, then pastes as usual. From the series shelf the
  recordings the episode lacks are first linked from the series' `media` paths (hash-checked),
  then from the source project, as today.
- **Remove from series shelf** takes the reference off the series file (and the `media` paths of
  a recording no other series entry uses). It never touches a recording or a project's entries.
  **Stop sharing** does the same for the shared shelf (exists).
- Between series and shared directly: no. Adopt into the project, then add. One path, fewer
  buttons.

## Duplicates

An entry is already on a shelf when an entry there has the same id, or the same references
(`refs` equal: the same recordings by hash, windows and layout) and the same length.
Adding it again changes nothing and says "already on the series shelf" (or shared). The
project shelf allows duplicates: it is a history.

## Missing media

An entry whose recordings the episode lacks shows "N recordings missing here", as on every
view today. It stays on the shelf: a recording on an unplugged disk comes back. A paste or a
place links what it can find and reports the rest; their clips are left out.

## No series

The Series view says "This project is in no series" with a **Series…** button (the dialog,
where one is chosen or made). **Add to series shelf** is disabled (its menu item greys out).
A project linked to a series whose file is not on this computer says "series file not found";
"Save as series defaults" writes it back (SERIES.md), with an empty shelf.

## Panel layout: one more view, not sections

The Clipboard tab already switches views. It becomes **This project · Series · Shared · Other
projects**. Sections in one list would triple the length of a narrow side panel and need three
filters; the view switch is one click and the filter box works the same in each.

- *This project* rows get a **Series** block button beside the star, pressed when the entry is
  on the series shelf (press again to take it off). Hidden when the project is in no series.
- *Series* rows: Paste here, Copy to this project, Remove from series shelf. Above the list:
  **Place on timeline** (the existing "Place series music" command).
- Paste choices (insert/overwrite, target tracks) apply to every view: paste forms work from
  any shelf because every paste goes through the project shelf.
- **Drag onto the timeline** (`ui/clipboard-drag.js`), from every view. While dragging: the
  target track's band tinted, a dashed outline per clip where it will land (the entry's layout
  kept, slots on the track and the ones below, as "paste on the current track"), the drop line
  (solid when snapped). The start or end snaps as when moving clips (clip edges, playhead, marks,
  8 px); Alt turns snapping off and a start inside a clip of the track stops at that clip's end.
  Esc (the browser ends the drag) or a drop off a lane pastes nothing. The drop is the same
  `clipboard_paste` as Mod+V at that frame and track, in the panel's paste mode (overwrite or
  insert), one undo step; In/Out play no part. An entry of another shelf is adopted first
  (series: linked from the series' paths), so missing recordings are linked in place and
  hash-checked as for every paste. Dragging a single clip of an entry: not yet.

## Commands (every one in a menu; no default keys)

Finnish layout rule: no default key that needs AltGr or Shift+digit, and `[ ] / = \` are
unusable. These commands are rare, so they get no default key; menu and palette only.

- Edit > Clipboard: **Clipboard: series shelf** (`clipboard.view_series`), **Add clipboard entry
  to series shelf** (`edit.series_shelf_clipboard`, the picked or newest entry; again to take it
  off), beside the existing views and Share.
- File > Series: the three series music commands, unchanged.

## Not in this round

- Reordering a shelf; renaming a series entry (rename it in the project, remove, add again).
- Dragging one clip out of a multi-clip entry (the panel lists entries, not their clips).
- Anchoring an outro to the programme's end (SERIES.md follow-up).
