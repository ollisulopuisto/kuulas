# Cart goes modal: no global number keys but In/Out

Owner, 2026-11-17: "in and out should be the only global numbered markers". Number keys act
inside their own panel; the timeline's 1 and 2 (Go to In/Out) stay the only number keys that
work everywhere.

The seven `clipboard.cart_play_n` commands and their Alt+1..7 keys are removed, together with
the Shift+Alt+1..7 assign keys. A cart slot still plays from a bare digit while the Clipboard
tab has the keys (`clipboard.play_slot_n`), from the entry's play button, and from
Playback > Cart. Assigning a number keeps its commands (`clipboard.cart_assign_n`): the
entry's number chip in the Clipboard tab, Playback > Cart, and the palette. The assign
commands stay in the keymap with no default key, so a user's own binding keeps working and a
new one can be set.

Keys reference and the design prototype regenerated from their canonical sources. Help's
record topic and the empty-slot toast now point at the chip and the menu instead of the old
keys. No project format or dependency changes; the engine keeps the seven slots.
