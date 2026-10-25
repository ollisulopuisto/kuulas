# M on a closed stretch

Owner request 2026-10-23 (BUGS #109): "if I click on the region at 21:09.618 and press M, I
only want THAT region to mute/unmute, not the entire parent clip".

## The problem

A stretch Auto-Silence closed is not a clip: it is a range in `Track.gate`, across the clips
of the track. M acts on the selected clips, and clicking the stretch selects the parent clip, so
M muted or unmuted all of it.

## The rule

With exactly one clip selected, an unmuted clip that does not keep the mic open, and the play
cursor (a click puts it there) inside a closed stretch of its track, M opens that stretch as a
clip of its own (`ops.open_gated_region`):

- the clips of the track are split at the stretch's two ends; a stretch across two clips gets a
  piece of each;
- the pieces inside are unmuted and flagged `ungated` (the mic stays open under them; the gate
  under them is removed, `normalize_ungated`);
- everything outside the stretch is untouched, and it is one undo step.

M again on that clip (it is selected and has its own edges now) mutes just it; M once more
unmutes it. So the cycle on a closed stretch is: closed by the gate, open as a clip, muted as
a clip, open again. A muted clip, or one that already keeps the mic open, is toggled whole as
before; so is any selection of more than one clip, or a cursor outside a closed stretch.

## Why not "mute the stretch"

A stretch the gate closed is silent already; muting it would change nothing you can hear. What
you want from M there is to open it, and the explicit muted clip comes with the second press, so
a later Auto-Silence run cannot reopen it (a clip flag survives; the gate is recomputed).

## Not done

No hover highlight of the stretch M would act on (the cursor decides, which the status bar's
cursor time shows); the Mute button of the Inspector still toggles the whole clip.
