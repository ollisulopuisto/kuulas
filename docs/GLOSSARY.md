# Terminology (English and Finnish)

One word for one thing, in the menus, hints, toasts, keys, help and docs. This file is the source;
`en.json` and `fi.json` follow it. Status: **draft for the owner's decisions** (18 Oct 2026). Hindenburg's
own Finnish words (from the owner's screenshot of Hindenburg PRO in Finnish) are listed where they exist,
because the owner knows them.

## The editing verbs (the confusing set)

| Meaning | Proposed English | Key | Proposed Finnish | Hindenburg (fi) | Notes |
|---|---|---|---|---|---|
| Take a stretch out and close the gap, nothing kept | **Delete and close the gap** | X | Poista ja sulje aukko | Tyhjennä (clear) / Leikkaa | no clipboard |
| Take a stretch out, close the gap, keep it on the clipboard | **Cut** | Cmd+X | Leikkaa | Leikkaa | the only one that fills the clipboard |
| Silence a stretch in place, the gap stays | **Mute selection** (today "Delete (keep the gap)") | Backspace | Mykistä valinta | (Delete leaves gap) | soft; can be undone by muting back |
| Mute or unmute whole selected clips | **Mute clips** (toggle) | N | Mykistä leike | – | |
| Copy to the clipboard, change nothing | **Copy** | Cmd+C | Kopioi | Kopioi | |
| Put clipboard content in | **Paste** (insert) / **Paste over** | Cmd+V | Sijoita / Sijoita päälle | Sijoita, Lisää | |
| Split a clip at the cursor | **Split** | B | Jaa | Jaa | |
| Copy, then mute in place | **Lift-cut** | Alt+X | (to name) | – | rarely used |

## Bus, group, clip, mix, export (decided WP74, owner 2026-10-19)

Checked against every `cmd.*`, `ui.*`, `error.*`, `stats.*` string in `fi.json` and `ui/help/fi/*.md`.

| Meaning | English | Finnish | Not |
|---|---|---|---|
| Tracks mixed together, with one fader, mute and solo | **bus** | **väylä** (Supista väylä, Väylän taso) | bussi, ryhmä |
| Clips (or tracks) the owner edits together | **group** | **ryhmä** (Ryhmitä leikkeet, Pura ryhmä) | väylä |
| Clips that keep their relative place to align them | **sync group** | **tahdistusryhmä** | |
| A stretch of audio on a track | **clip** | **leike** (leikkeen, leikkeitä) | klippi, pätkä |
| The rendered programme, one file | **mix** | **miksaus** (to mix: miksata) | |
| Writing files out | **export** | **vienti**, verb **vie** | |
| A track's ducking written as automation | **ducking (automation)** | **vaimennus (automaatio)** | "automix" |
| The external mixing tool | **automixer** | **automixer** | automiksaus |

"Bus" is never "group" and "group" is never "bus": "Collapse the bus" is "Supista väylä" (a
bus is collapsed to one row), "Group clips" is "Ryhmitä leikkeet". The verb "ryhmitellä" is not
used for putting tracks on a bus: they are moved there ("Siirrä valitut raidat uuteen väylään").

## Marks and time

| Meaning | English | Finnish today | Hindenburg (fi) | Decision needed |
|---|---|---|---|---|
| The start of the marked range | In point | Alkupiste / Alku | Sisään | Alku/Loppu/Pituus or Sisään/Ulos/Aika |
| The end | Out point | Loppupiste / Loppu | Ulos | |
| Length between them | Length | Pituus | Aika | |
| Narration to be recorded | Narration | **Juonto** (decided 18 Oct) | – | |
| A clip on a track | Clip | **leike** (decided 19 Oct; "klippi" and "pätkä" are gone) | (region) | done |

## To do (WP62)

1. Audit every label, hint, toast, menu title and help topic for these words; make a table of the
   present strings and the changes (a script that lists all `cmd.*`, `ui.edit.*` and toast keys per word).
2. Owner decides the open rows above; then change `en.json` and `fi.json` together, in one commit, with the
   Finnish review (`docs/handoffs/fi-review-2026-10-18.md`) folded in.
3. A test that fails when a banned old term returns (a small list of forbidden strings per language).
