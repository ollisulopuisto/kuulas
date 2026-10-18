# kuulas mark

Status: in the app since v26.10.18.32 (a first version, not final).

The mark: a disc made of nine vertical bars (a waveform) with one bar missing and a round hole
in the lower right, whose edges sit in the gaps between bars so no bar gets a sliver ("Z2" in the
design rounds). Colour is the apple green `#8CBF3F`, a placeholder not yet tied to `ui/tokens.css`.

- `ui/logo.svg` (also `docs/design/logo/kuulas-disc-9.svg`): nine bars, the header and large sizes.
- `ui/favicon.svg` (`kuulas-disc-7.svg`): seven bars, the favicon and small sizes.
- `kuulas-mark-9/7/5.svg`: the earlier apple-in-a-waveform direction, kept for reference.

App icons (v26.10.18.33): `src/kuulas/assets/icons/` holds the PNG set, `kuulas.ico`,
`kuulas.icns` and the dock image, all made by `scripts/make_icons.py` (run it on macOS; it is
also the single source of `ui/logo.svg` and `ui/favicon.svg`). The launcher page and the macOS
Dock icon show the mark.

Decided by the owner (2026-10-18): the hole position (lower right) is perfect.

Open: nothing reads
as more than a dotted ring at 16 px; the Dock label says "Python" until the app is packaged
(a real .app bundle); the icons have not been looked at on a real Dock or Windows taskbar;
colours are placeholders.
