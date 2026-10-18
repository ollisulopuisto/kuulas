---
id: automix
title: Mixing with the automixer
applies-to: []
commands: [export.automix]
related: [track, timeline]
---
The automixer mixes the finished edit for you: speech levelled and polished, music ducked under it, the whole thing at a target loudness. Kuulas hands it the edit as separate tracks, so you do not export or move any files yourself.

- Start it from File, Mix with the automixer, or the command palette: {key:export.automix}
- Set the target loudness, and optionally where an ad spot goes and how long it is.
- It runs in the background. The notice shows the automixer's latest message; Cancel stops it.
- The mix is saved beside the project, named after the edit and the time. Show in Finder opens the folder.

Full episodes may need a lot of memory. Try a range first.

The first time, check the command under "The automixer" in the dialog. It is the program kuulas runs, normally `uv run automixer` in your podcast folder. A missing program gives a message that names it.

Tracks that are muted, or not soloed while another is, are left out, as in any export. See also [[track]].
