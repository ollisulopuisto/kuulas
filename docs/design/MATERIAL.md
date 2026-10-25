# Material: the project's recordings list

Owner request 2026-10-23 ("all the material that is in the project"), the Recordings list
of WP12e and BUGS #82. A design note, nothing built. Recommended as its own side-panel tab,
**Material**, next to Inspector, Candidates, Clipboard, Markers and History.

## What it is, and what it is not

- The list of **whole recordings** in the project, every file the project points at: imported
  files, recorded takes, excerpts. The Clipboard holds **pieces** you copied; Project
  properties hold **settings**. This is a working list you act on.
- It makes things recoverable without Undo: a take replaced by a later take, a question
  recorded and never used, a file whose clips were all deleted. A recording is never removed
  from the project by deleting its clips (ground rule 17); this is where it stays visible.

## One row per recording

- Name (the file's, or "Take 3" for a take), length, source (imported / recorded / excerpt of),
  the track it was recorded for, when.
- **How much the edit plays**: used, cut and unused seconds, from `source_map.coverage`
  (already used by the Inspector's Source view); a thin bar shows them on the recording's
  length. A recording used nowhere says "Not on the timeline".
- Takes of one recording session are grouped (a group header "Take 3" with its channels), so a
  multitrack take is one entry, not one per mic.
- A missing file shows the missing state of the timeline (red) and offers Locate / Relink.

## Actions (a row, and a context menu; every command also in a menu)

- **Play** (preview, like a Clipboard chip), **Place on the timeline** (at the playhead, on the
  track it was recorded for or the chosen one; overwrite or insert, as the paste modes), **Copy
  to the clipboard** (the whole recording as an entry), **Reveal in Finder**, **Locate / Relink**.
- Select a row to show where it is used (the Inspector's Source view for that recording) and to
  jump to the first place it plays.
- Nothing here deletes a file. "Remove from the project" is a later, separate decision (it only
  forgets a recording nothing uses; the file stays on disk).

## Filters and order

All, On the timeline, Not on the timeline, Takes. Newest first by default; name and length as
alternatives. A text filter on the name.

## Not decided

- Whether Material and the Cut/Unused hits of the transcript search ("Not in this edit") share
  one source list (probably yes: the same rows, reached from a word).
- Whether the Selects edit (R63) builds on this list or has its own.
- The tab's key (Cmd+6 is the next in the row) and its place in the tab order.

## Tests to write first

A pure model (`ui/material-model.js`): rows from the project and `coverage` answers, grouping of
a multitrack take, the filters, the sort; a server route `GET /api/material` with the same data;
and a test that no action changes a recording or the project's media list.
