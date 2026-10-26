# Toolbar: a docked rail for discovery

Owner, 2026-10-26: new users cannot find what kuulas can do (Auto-Silence is the example), and the
menus hide it. A toolbar is a discovery device: every button says "this exists" and its tooltip
says which key runs it. Not built; this page is the design, WP86 in `PLAN.md` is the build.

## Decisions (owner)

- **Docked, not floating.** A rail on the left edge of the window, left of the tracks. Nothing in
  kuulas floats; the rail is one more dock.
- **Groups:** session (undo, redo), track, clip. Not File: the menu is enough for that.
- **Ten buttons to start**, each with a reason. The bar must not grow into a second menu.
- **Icon only, or icon and text.** Text helps discovery, the icon saves space. The choice is per
  user, remembered, and has a switch in the View menu.
- **Positions never change unless the user changes them.** This is the rule that matters most for
  discovery: a button that moves cannot be found again. See "Stable positions" below.
- **Usability first:** a button that cannot run is greyed and stays where it is; the tooltip names
  the key (the app's own tooltip, `ui/tooltip.js`). Text in every language from the start (R39).
- **Every button is a command from the same registry as the menus**, so a new command needs no
  toolbar work, and the menu-coverage test keeps its meaning.

## Stable positions

Other editors let the user arrange the bar: Reaper (every toolbar), Logic Pro (the control bar),
Photoshop (Edit > Toolbar), Office (the Quick Access Toolbar). The warning is Office's adaptive
menus, which moved rows by use and were disliked and then removed. So:

- Only the user moves a button: drag to reorder (a drop line shows where the button lands; Esc cancels; Alt+Up/Down moves the focused button one place), "Add to toolbar" on the
  right-click menu of any menu row, "Remove from toolbar" on the button's right-click menu
  (built). A new pin goes to the end, or where it is dropped.
- A disabled button is greyed, never hidden or moved.
- A state badge (the Auto-Silence count, Follow on or off, sync) changes the button's content,
  never its place.
- Usage hints never reorder the bar and never add a button.
- View > "Reset toolbar" restores the default order.

## The first ten (a guess, to be tuned; the owner confirms the list)

By workflow, top to bottom, so the rail reads as a checklist:

| # | Button | Why it is here |
|---|---|---|
| 1 | Undo | the most used button in Audacity |
| 2 | Redo | pairs with Undo |
| 3 | Import | the first step |
| 4 | Transcribe | the step that unlocks text editing |
| 5 | Auto-Silence | the feature people do not know exists; badge: how many silent stretches |
| 6 | Split | the most common cut |
| 7 | Quick mute | the N key and the Alt-click that go with it |
| 8 | Resync the range | the sync function used most |
| 9 | Automix | the mix step |
| 10 | Export | the last step |

Commands are named here, not numbered: the ids come from `ui/menu-model.js` when WP86 starts.

## Beside the toolbar

- **Command search field** at the top of the rail, "Search command...". It uses the command search
  of WP75, so not everything has to be a button.
- **A visible search field in the transcript's header.** `ui/transcript.js` already has a find bar
  (`findBar`, `openFind`); whether it is only a key away is to be checked. Search in deleted
  material (WP82) is an option of that field, not a button.
- **Hints from use.** After, say, ten hand mutes: "Auto-Silence does this for you", once. The
  counter is local only. The hint does not touch the toolbar.

## Open questions

- The final ten buttons, and the icons (the icon set is not chosen).
- The rail's width with text, and what happens in a narrow window (collapse to icons only).
- Where the rail sits against the track headers: left of them, or inside the header column.
- Whether a first-run tour is wanted; it is not part of WP86.
