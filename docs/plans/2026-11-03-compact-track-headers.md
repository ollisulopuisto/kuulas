# Compact track headers

## Goal

Keep a stable, narrow track column with speaker color/name and M/S targets always visible. Reveal gain, pan, routing, and role controls in a positioned overlay on hover or keyboard focus; allow explicit pinning for pointer and touch use. Opening controls must not resize the track column or move the timeline.

## Implementation sequence

1. Add pure state tests for hover/focus reveal, pinning across pointer exit, and Escape dismissal. Run them red first.
2. Reduce the track header column to about 160 CSS px (plus the toolbar rail), retain the track label and M/S buttons at fixed positions, and add an accessible disclosure/pin button.
3. Render the active track's full controls in a fixed overlay anchored to its header, keeping the controls reachable as the pointer moves into the overlay. Keep bus headers unchanged.
4. Add localized English/Finnish disclosure text and update design/roadmap notes.
5. Run the focused test, full Node suite, pytest/Ruff, and Biome; fix failures before landing.

## Implementation notes

- Mixer controls are rendered in a body-level fixed overlay, anchored to the track header.
- Hover/focus reveal is transient; the disclosure button pins or unpins the current track.
- Tab from the disclosure enters the overlay's first available control.
- Full Node UI suite passes. Python checks use the existing project venv because network DNS
  prevents uv from fetching `hatchling`; Biome's npm package fetch is blocked by registry DNS.

## Acceptance checks

- Opening/pinning the overlay never changes the editor grid's header width or timeline origin.
- Name, speaker-color stripe, M, and S remain visible and do not move when controls open.
- Hover and keyboard focus open controls; the explicit button pins them; Escape closes them.
- Controls stay interactive while focus/pointer is inside the overlay and are positioned again after scroll/resize.
- Compact density and bus headers retain their existing behavior.
