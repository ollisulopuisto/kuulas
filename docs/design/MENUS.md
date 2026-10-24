# Menu structure for first-time users

Owner request 2026-10-24: the menus are unwieldy (a power tool, but first-time users must find the
few things they use). Opus design review, read from `ui/menu-model.js`, `ui/tests/menu-layout.test.js`
and `docs/KEYS.md`; nothing here is built except the Cart move and the shortcut flash (see the end).

## The state in numbers (before 2026-10-24)

301 commands in 8 top-level menus; the bar order is pinned: File, Edit, Clip, Track, Text, Playback,
View, Help.

| Menu | Top-level rows | Commands incl. submenus | Biggest submenus |
|---|---|---|---|
| File | 24 | 39 | Export transcripts 9, Series 7 |
| Edit | 14 | 65 | Clipboard 26, Select 13 |
| Clip | 13 | 27 | Sync 7 |
| Track | 17 | 33 | Auto 10, Bus 8 |
| Text | 12 | 25 | Cut candidates 10 |
| Playback | 15 | 60 | Go 26, Markers 10 |
| View | 17 | 42 | Zoom and fit 9, 8 submenus |
| Help | 6 | 10 | |

Offenders: the Cart sat two submenus deep (a bug, fixed: the bar draws one level); Go has 26 items, 7
of them History commands that are not navigation; File's flat export run (9 items); Track's flat role
and bus run; View mixes about 10 preference toggles with display commands; Text has 10 flat items with
no separators.

## Usage tiers

- **First hour:** New, Open, Open Recent, Import, Save, Play, Play selection, Record, Undo/Redo,
  Cut/Copy/Paste, Delete, Select all, Find, Split, Merge, Mute, Fade, Add track, Mute/Solo track,
  Transcribe, Delete words, Zoom/Fit, Export mix, Export (options)…, Preferences, Help search.
- **Regular (second week):** Auto-Silence, automix and Duck, Export with automixer, Clipboard, Cart,
  Markers, in/out, Go to, Jump to time, Focus mode, Series, Trim/Nudge, Group, Bus, Level/pan, Quick
  mute, Paste variants, Select variants, Cut candidates, Placeholders, Side panels, Loop, Fast/Slow/Shuttle.
- **Rare:** Sync, drift, Relink/Locate media, Colab, Record settings, Statistics, music report, cut
  list, transcript exports, Open earlier version, Backup, Send a copy, History restore, track roles,
  gate commands, silence learn, block level, Inactive style, Mouse, Pause break, Reset remembered,
  clipboard limit, re-sync confirm, Keymap import/export, Log level, Performance report.

## Proposal (the bar keeps its 8 menus in the same order)

- **File** (about 14 rows; changes the pinned File order, the owner's call): New, Open, Open Recent ›,
  Close; Import, Locate media; Save, Save named version, Versions › (Open earlier version, Backup now,
  Send a copy); Export mix, Export mix (options)…, Export with automixer (keys unchanged); More
  exports › (range, all tracks quick/…, automixer log, subtitles, transcript, chapters, regions,
  narration script, music report, cut list); Series › (contents unchanged), Statistics…; Preferences…
- **Edit:** the top-level order stays; the Clipboard submenu shrinks to about 12 items (the Cart left).
- **Clip:** unchanged.
- **Track** (17 to 11 rows): add, rename, delete empty; mute, solo; Role › and Bus › demoted; Auto › unchanged.
- **Text** (12 to 9 rows): Transcribe ›, delete/remove/cut words, correct, find removed, mark candidate,
  Placeholders › demoted, Cut candidates ›.
- **Playback** (about 13 rows): play family, Record…, Record settings ›, loop family, one Speed › (Fast,
  Slow and Shuttle merged), Go to › (19 items; History and panel prev/next leave), Jump to time,
  Markers ›, Cart › (done).
- **View** (about 12 rows): Zoom and fit ›, Side panels ›, History › (from Go), Focus ›, Buses ›, words
  on clips, Follow, Show playhead, Options › (Mouse, Inactive style, Pause break, clipboard limit,
  re-sync asks first, Reset remembered), Language, Command palette, Minimise.
- **Help:** search, Getting started (new), Help, Keys, Keymap ›, Performance report, Log level.

Rejected: a "basic" menu set or a hold-a-modifier-to-see-everything mode (it breaks "menus show
everything", Alt and Shift already swap items, and the menu paths Help search shows would change).
Instead: the first-hour item first in each menu, the rare ones in submenus at the bottom.

## Helping a first-time user

- "Where is that command?" already exists: Help search (Shift+Cmd+K) shows the menu path, and
  Alt+Enter opens the menu at the item. `findItem` must cover every depth that exists (it searches
  one level, which is why nesting is now forbidden by a test).
- **Help > Getting started:** about 6 items (Import, Play, Split, Transcribe, Export, Search commands)
  that run the real commands and show their keys. Cheap; later it opens the tour (R60/WP48).
- **Flash the menu title when a shortcut runs**, as macOS does: built 2026-10-24 (chords with Cmd,
  Ctrl or Alt only, about a quarter of a second, off when motion is off).

## Risks and tests

`ui/tests/menu-layout.test.js` pins File order (17-48), Export transcripts (62-74), sync.confirm in
View (117-128), Text shape (167-186), the Fast playback submenu (227-230), View submenus (231-250),
the Playback submenu list (269-286). Migration is data only in `menu-model.js` (about 120 lines moved),
about 8 new submenu label keys (en + fi), about 120 test lines rewritten, and a sweep of help topics
that name menu paths. No command id or default key changes, so the Finnish-layout rule is untouched.

## Questions for the owner (open)

1. May File's pinned order change (Versions ›, More exports ›)?
2. Cart in Playback rather than Edit > Clipboard? (done as the fix; say if you want it elsewhere)
3. History out of Go into View?
4. May `sync.confirm` go under View > Options (breaks the "dialog switch is in View" pin)?
5. Merge Fast, Slow and Shuttle into one Speed submenu (breaks the test at 227)?
6. Settings in a Kuulas app menu (Apple's guideline) instead of File? (unverified what the native app
   menu holds today; ROADMAP says only Quit, Hide and Fullscreen.)
7. Build Help > Getting started?
