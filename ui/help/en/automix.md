---
id: automix
title: Mixing with the automixer
applies-to: []
commands: [export.automix]
related: [track, timeline]
---
The automixer mixes the finished edit for you: speech levelled and polished, music ducked under it, the whole thing at a target loudness. Kuulas hands it the edit as separate tracks, so you do not export or move any files yourself.

- Start it from File, Export mix (automixer)…, or the command palette: {key:export.automix}
- Set the target loudness, and optionally where an ad spot goes and how long it is.
- It runs in the background. The notice shows the automixer's latest message; Cancel stops it.
- The mix is saved next to the project's .kuulas folder (in the folder that holds it, never inside it), named after the edit and the time. The dialog can name another folder. Show in Finder opens the folder.

Only speech and music tracks are mixed. Buses are for your own monitoring balance and for burn-in exports to another app; the automixer does not use them, so they are left out of this job (the normal exports are unchanged). Track faders and pan are not applied either: the automixer levels the tracks and spreads the speakers itself. Clip gain and your edits are. Your recordings can be in any format and sample rate, since kuulas renders them for the automixer; the project itself must be 48000 Hz. The mix is a 16-bit WAV.

The first time, check the command under "The automixer" in the dialog. It is the program kuulas runs, normally `uv run automixer` in your podcast folder. A missing program gives a message that names it.

Tracks that are muted, or not soloed while another is, are left out, as in any export. See also [[track]].
