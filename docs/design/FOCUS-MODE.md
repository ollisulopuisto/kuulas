# The range scope as lane size (owner's "E focus" idea)

Design review, 21.10.2026. Status: the E resize is **not built and not wanted** (owner, 21.10:
E does not resize; the band and bars go on scoped lanes only, done v26.10.20.22). F, the deep
focus of section 7.3, is **built**: see section 8. Mock:
[`focus-mode-mock.html`](focus-mode-mock.html) (open it in a browser, click headers, press E).

Owner's idea: "When you press E, the other channels take up slightly less space and the
active channel takes up more space. And you could even animate the change."

## 1. The problem, stated

**At a glance, before pressing X, M or Backspace, the user must know which tracks the next
range operation will touch.** Everything else is secondary. Today (`ui/range-scope.js`,
WP83) the only cues are a veil over the other lanes (`DIM_ALPHA` 0.72 in `timeline.js`),
headers at 35 % opacity, and the status-bar chip. Dimming is a weak "where": a dark lane
reads as "quiet speaker" as easily as "out of scope", and 0.72 hides exactly the faint
bleed you need to see.

A second, different wish hides in the idea: **"give me more room for the track I am
working on."** That is the view focus of WP28 (F, 16 px strips, `ui/focus-layout.js`,
not wired). The two must not be merged: E is flipped many times an hour mid-edit, F is
"work on Ville for ten minutes".

## 2. Verdict: yes, but bounded

Yes: size is the strongest pre-attentive cue there is, it is not colour, and it survives a
glance from across the desk. But only within limits, because:

- **The other lanes are context.** Cross-talk and bleed decide where a cut is safe. A
  context lane must keep its name label (hidden below 40 px), the words row
  (`WORDS_MIN_LANE` 52) and some waveform: **never under 56 px**. "Slightly" means 75 %.
- **Spatial stability.** The user's map is "Anna top, Pekka third". Order never changes,
  bus rows and group gaps never resize, and **the total height stays the same**, so
  nothing scrolls away and the lanes below the group do not move.
- **The clicked header must stay under the pointer.** With one or two tracks in scope and
  the 75 % rule, the clicked lane's new extent contains its old one (true for every case
  in the table below); the layout function must guarantee it (a test).
- **Layout jumps cost.** Section 20 of GUI-DESIGN.md: one animation at a time, nothing
  moves a target about to be clicked, nothing animates during playback. So: 120 ms, never
  during a drag, snap (no animation) while playing.
- **Size alone is not enough** for "which tracks": with 2 of 5 in scope the two grown
  lanes are not adjacent and size differences of 1.3x read as "lanes I resized". So the
  primary marker is an **accent edge bar** on in-scope headers and lanes; size reinforces.

## 3. Alternatives

| | Design | Solves "what will X touch?" | Solves "room to work" | Pros | Cons / risks |
|---|---|---|---|---|---|
| A | Veil only (today) | weakly | no | no movement, built | dark = quiet or out?; 0.72 hides bleed; colour/luminance only |
| B | Owner's idea literally: grow + shrink, unbounded | yes | yes | strong cue | context lanes can get unreadable; headers jump; fights manual lane heights |
| C | Others collapse to 16 px strips (WP28 style) | yes | strongly | max room | bleed invisible: wrong tool for cutting; violent on a toggle pressed often |
| D | Accent edge bar on in-scope lanes, no resize | yes, if the bar is wide | no | zero motion, cheap | easy to miss with 4-5 lanes; needs veil to carry the "not" side |
| E | Header-only emphasis | no (eyes are on the waveform) | no | trivial | the header column is not where the user looks when pressing X |
| **F** | **D + bounded resize (B within limits) + lighter veil** | **yes, redundantly** | **some** | size, shape and text agree; context stays readable | layout animation costs a redraw per frame; one more thing to keep in step with drags |

## 4. The design (F)

**Layout rule** (pure, beside `layoutRows` in `lanes.js`, a view layer: never written to
`laneHeights`, not in history or the project file):

- Applies only when the scope source is `"selected"` and 1 ≤ k < n tracks are in scope,
  and the base lane height is ≥ 64 px (compact density, 40 px: no resize, bar and veil only).
- Each out-of-scope lane: `max(56, round(0.75 × its base))`.
- The freed height goes to the in-scope lanes in proportion to their base, each capped at
  2 × its base; any rest goes back to the context lanes. The sum is unchanged.
- Numbers at today's ~115 px, 4 tracks (sum 460): 1 in scope = **202** / 86 / 86 / 86;
  2 in scope = 144 / 144 / 86 / 86. 5 tracks, 2 in scope (sum 575): 158 ×2, 86 ×3.
  Laptop, 5 tracks auto-fit to 72 px: 1 in scope = 144 / 56 ×4.

**Events**

- **Header click:** select that track (existing rule), scope narrows, lanes ease to the
  new heights. Clicked header stays under the pointer.
- **Cmd+click another header:** it joins; both share the grown space (144/144 above).
  Cmd+click a selected one removes it; the last one removed returns to all (existing rule).
- **E:** flip all ↔ selected. To "all": lanes ease back to equal, bars off, veil off. Back
  to "selected": the remembered selection returns with its sizes. Selected mode with
  nothing selected: no resize, no veil, amber chip (as today).
- **Esc:** clear the selection, all tracks, equal heights.
- **Lane or clip click:** makes the track current only, as today: no resize.
- **Range painted across lanes** (`source: "lanes"`): no resize; the band shows it.
- **Lane-grip drag** while scoped: changes that track's base height; the rule reapplies.

**Motion.** Heights tween over `--dur-layout` (120 ms) with `--ease-standard`; canvas and
header column from one rAF loop so they never disagree. During the tween the waveform
tiles are drawn stretched, then re-rendered at the final height. Animation "subtle":
the same 120 ms (it is already short). "Off" or `prefers-reduced-motion`: instant.
While playing: instant (section 20). This breaks section 20's "transform and opacity
only" performance note; accept it for 120 ms and check it with the long-task monitor.

**Scroll and playhead.** Horizontal: nothing changes, the playhead stays put. Vertical: if
the lanes scroll, keep the top of the current track at the same screen y; if an in-scope
lane would end up off-screen, scroll the minimum to show it.

**Drags in progress.** E pressed during a clip drag, edge drag or range drag: the scope
(and chip) change at once, the heights wait until the pointer is released, so the lane
under the pointer and the drop target never move mid-drag.

**Veil.** Lower `DIM_ALPHA` from 0.72 to **0.5** and header `.scope-dim` from 0.35 to
0.6: size and bar now carry part of the meaning, and bleed must stay visible. (A guess;
check on real audio.)

**Collapsed buses.** Bus rows, ribbons and gaps keep their height. A collapsed bus is never
expanded by the scope; its ribbon strips for out-of-scope members get the veil, in-scope
members get the bar on the ribbon. The chip names the folded track: "on Ville (in
Voices, folded)".

**Status chip** (role `status`, polite, so a screen reader hears the change):
- selected: `range operations on Anna, Ville · E: all tracks`
- all, with a remembered selection: `range operations on all 4 tracks · E: only Anna, Ville`
- none selected: unchanged amber `no tracks selected: nothing will be touched`

**Not colour alone.** Four independent cues: size, the 4 px bar (shape, present/absent),
the "● range" tag in the header, and the chip text. Headers are a multi-select listbox
(`aria-selected`), Enter/Space on a focused header selects, Cmd+Enter adds.

## 5. Wireframe, 4 tracks, Ville in scope

```
BEFORE (all tracks)                      AFTER (E / header click on Ville)
┌───────────┬──────────────────────┐     ┌───────────┬──────────────────────┐
│ ▾ Voices  │░░░░░░ bus ░░░░░░░░░░░│ 28  │ ▾ Voices  │░░░░░░ bus ░░░░░░░░░░░│ 28
├───────────┼──────────────────────┤     ├───────────┼──────────────────────┤
│ Anna  M S │▁▃▇▅▂▁  ▁▁ ▁ ▁▂▁▃▆▇▃▁ │115  │ Anna  M S │▁▃▇▅▂ ▁ ▁▂▁▃▆▇▃▁ (dim)│ 86
├───────────┼──────────────────────┤     ┣━━━━━━━━━━━╋━━━━━━━━━━━━━━━━━━━━━━┫
│ Ville M S │▁ ▁ ▂▆█▇▅▃▂▁ ▁ ▁▁ ▁   │115  ┃ Ville ●rng┃       ▃▆█▇▅▃          ┃
├───────────┼──────────────────────┤     ┃ M S       ┃ ▁ ▁ ▂▆█████▇▅▃▂▁ ▁ ▁▁ ┃202
│ Pekka M S │ ▁  ▁▁ ▁ ▂▁ ▁▃▅▆▃▁  ▁ │115  ┃           ┃       ▃▆█▇▅▃          ┃
├───────────┼──────────────────────┤     ┣━━━━━━━━━━━╋━━━━━━━━━━━━━━━━━━━━━━┫
│ Theme M S │▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂│115  │ Pekka M S │ ▁ ▁▁ ▁ ▂▁ ▁▃▅▆ (dim) │ 86
└───────────┴──────────────────────┘     ├───────────┼──────────────────────┤
 status: (no chip)                       │ Theme M S │▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂ (dim)  │ 86
                                         └───────────┴──────────────────────┘
                                          status: [range operations on Ville · E: all tracks]
```
(┃ = the 4 px accent edge bar; the sum stays 488 px.)

## 6. How to test it (owner)

1. Open the mock, click Ville, then Esc, ten times fast: does it feel calm or jumpy?
2. Cmd+click Pekka with Ville selected: can you still tell both apart from the others?
3. In a real cross-talk spot, are the 86 px context lanes enough to see Anna's bleed
   under Ville before you cut? Try "Resize" off in the mock to compare with bar-and-veil only.
4. On the laptop (5 tracks auto-fit): is 56 px still readable?
5. When built: press E mid clip-drag, during playback, and with Voices collapsed.

## 7. Open questions (with my default)

1. **Shrink ratio**: 0.75 or subtler 0.85? *Default 0.75; 0.85 is hard to notice.*
2. **Animate while playing?** Section 20 says no. *Default: snap while playing.*
3. **E vs F (WP28)**: keep both, with F the strip-mode deep focus? *Default yes; F reuses
   the same layout function with `ratio → strip 16 px`; E never goes below 56 px.*
4. **Veil 0.5 / header 0.6** instead of 0.72 / 0.35? *Default yes, verify on real bleed.*

## 8. Focus mode (F, WP28) as built, 21.10.2026

What was missing against WP28 and this note, and is now built:

- **Commands**, all in View > Focus mode, en + fi, help topic `focus`:
  `view.focus` (Shift+F), `view.focus_solo` (Alt+Shift+F), `view.focus_hide_others` (Alt+F, a
  switch), `view.focus_shrink` (a switch, no key).
- **Layout**: `focus-layout.js focusHeights` gives every lane with a row a height: the focused
  speaker's lanes share the lane area, the others share 40 % of it (`sideHeight`: 16 to 64 px
  each; owner 2026-10-23, 16 px strips were "a BIT too extreme"), bus rows and gaps keep their
  height. It is a view layer (`state.focusHeights`, read by `lanes.js layoutFor` as
  `viewHeights`, not clamped up to MIN_LANE): never `laneHeights`, history or the project.
- **Motion**: the `focus-resize` cue (motion.js): 120 ms ease-out, shorter at "subtle", instant
  with Animation off, reduced motion or while playing. A change while a pointer is held waits
  for the release, so nothing moves under a drag.
- **Inactive look**: lanes out of focus get the same look as lanes outside a range operation
  (`inactiveTracks` = range scope's set plus focus's), canvas and headers alike. With the
  shrink switch off this is all focus mode does to the lanes.
- **Strip headers**: below 24 px a header keeps only its name, small (`.track-header.strip`).
- **Walking**: Up/Down (track.prev/next) walk the focus by speaker (`walkFocus`); a click that
  makes another track current moves the focus to that track's speaker (`followCurrent`).
- **Solo**: Alt+Shift+F remembers the solo set, solos the focus (and follows it while
  walking), and leaving puts the old set back, as additive solo edits the server merges into
  one undo step (`soloSteps`).
- **Transcript**: other speakers' paragraphs are dimmed; with the switch, hidden (height 0 in
  the virtual list, so scrolling stays right).
- **Esc**: leaves focus after the marks are cleared (`escape.js` "leave_focus").

Choices made where the design was open (simplest, change if wrong):

1. **Key.** WP28 says F, but F is Fit selection (owner, 2026-10-18). Focus is Shift+F (owner 2026-10-21: plain F stays Fit selection: it is used far more often than a mode toggle), focus
   and solo Alt+Shift+F (WP28 had Shift+F). Nothing needs AltGr or Shift+digit.
2. **Esc order.** Esc first clears the track selection, then the clips and the marks, and only
   then leaves focus, so a focused edit session survives the usual Esc presses.
3. **Lane cap.** The focused lanes are capped at MAX_LANE (360 px); in a tall window the room
   below the last lane stays empty rather than drawing an 800 px waveform.
4. **Collapsed bus.** A focused track folded in a collapsed bus is not unfolded: no resize then,
   only the inactive look and the transcript. Unfold the bus to see it.
5. **Shift+F while focused** leaves focus whichever variant is pressed.
6. **Waveform redraw during the tween**: the waveform layer redraws at each step (no stretched
   tiles yet). If the long-task monitor shows jank, draw stretched tiles during the 120 ms.

Not built (parked): the focused track's automation band drawn tall under its waveform (WP28
bullet "editable band"), and v2's focus history and focus that follows the talker.
