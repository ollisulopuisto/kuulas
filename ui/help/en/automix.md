---
id: automix
title: Mixing with the automixer
applies-to: []
commands: [export.automix, transport.render_listen]
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

**A quick preview of a range.** A whole automix takes about as long as the edit is long. To hear a change sooner, set In and Out around a stretch and tick "Only the In/Out range (a quick preview)": only that range is mixed, in a few minutes for a couple of minutes of edit. The file is named like a whole mix plus "preview" and the range, and never replaces a whole mix. Levels, speaker balance, the music bed's level and the mastering are measured on the excerpt alone, so the preview is an approximation for listening, not the final mix.

**Listen to the rendered mix.** After a mix, the transport corner shows Edit | Rendered mix (also Playback > Listen to the rendered mix). Rendered mix plays the file in place of the tracks, at its place on the timeline (a range preview where the range is), so Play, seek, loop and fast listening work as usual and you hear everything the automixer did. A band over the lanes says what is playing; Back to the edit, or Edit, returns. Mute, solo and gain are dimmed meanwhile: they do not change the file. The file is mastered (about -16 LUFS), so it sounds louder than the edit; levels are not matched.

The render matches the edit only while the edit still sounds as it did: any change to clips, gains, mutes, gates, ducking or track and bus settings makes it stale, and listening goes back to the edit by itself and says so. Markers, names and the playhead do not count. A stale or missing render stays listed (Rendered mix is greyed out and says why) until the next mix; its file is never deleted.
