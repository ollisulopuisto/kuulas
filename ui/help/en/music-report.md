---
id: music-report
title: Music report for Teosto and Gramex
applies-to: []
commands: [export.music_report]
related: [track, clip]
---
The music report lists every piece of music the open edit actually plays, for royalty reporting (Teosto, Gramex). Open it from File, Music report…, or find it in the command palette by typing "Teosto", "Gramex" or "musiikkiraportti".

What counts as heard: clips on music tracks, leaving out muted clips, muted tracks and stretches that a gate or the track's automation has silenced. Consecutive pieces of the same recording with a gap under 2 seconds count as one use.

Each row has the title, artist, composer, publisher, ISRC and file name from the recording's tags, the programme time where it starts and ends, the duration, and whether it plays under speech (Background) or not (Featured). Times are whole seconds from the start of the programme, and a part of a second counts as a whole one, so the start, the duration and the end always agree.

- Save CSV… and Save HTML… make the files, named after the project, e.g. "My show music-report.csv". The CSV uses semicolons and opens correctly in Finnish Excel. A file that already exists is never overwritten: your browser or the desktop window gives the new one its own name.
- Copy as table puts the report on the clipboard, tab separated, so you can paste it into a spreadsheet.
- A piece with no title or no artist is listed under the summary, by name, and its row is tinted. Fill in the tags before you send the report.
- An edit with no music says "No music in this edit" and why: there is no music track, the music tracks are muted, they have no clips, or the music is silenced.

The report is for the edit that is open now. It never changes the project or your recordings. See also [[track]] and [[clip]].
