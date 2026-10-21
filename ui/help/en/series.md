---
id: series
title: Series: settings shared by episodes
applies-to: []
commands: [series.dialog, series.save, series.apply, series.new_episode, series.music_add, series.music_place, series.music_clipboard, clipboard.view_series, edit.series_shelf_clipboard]
related: [track, automix]
---
A series is the episodes of one show, recorded in the same place. What you found for one episode is the right start for the next: the tracks (their names, roles, buses, gain, pan and mono), the Auto-Silence options and the automixer's de-bleed values. All series commands are in File, Series.

- Save as series defaults… copies this episode's values to its series. A project in no series asks for a name and starts one.
- Apply series settings brings the series' values back into this episode as one undo step. It adds the tracks that are missing and sets the values of the tracks of the same name; it never removes a track or a clip.
- New episode from series… makes a new project with the series' tracks and settings, named as the next episode, beside this one.
- Series… shows which series the episode belongs to and what differs from it, and lets you choose, rename or leave it. The status bar shows the series and says when the episode differs.

Nothing is applied by itself: settings change only when you run one of these commands. Each project keeps its own copy of the series' values, so it opens and works the same when the series file is not on this computer.

Series music: select the intro, outro or bed clips and run Add selected clips to series music. In a new episode, Place series music on the timeline puts them where they were, on the tracks of the same name, or Put series music on the clipboard lets you paste them yourself. The series keeps references to the recordings, never copies; your recorded files are never changed. See also [[track]] and [[automix]].

The series music is also the Clipboard's series shelf. The Clipboard tab has four views: This project (every copy and cut), Series (the series shelf), Shared (for every project) and Other projects. Press Series on an entry of this project to put a copy on the series shelf, and again to take it off; the project's own entry stays. On the Series view, Paste here and Copy to this project work as on Shared, with the paste choices above, and Place on timeline places them all. Drag an entry from any view onto a track to paste it there, in the paste mode chosen above; it snaps as when moving clips. An entry already on a shelf is not added twice. Taking an entry off a shelf never touches a recording.
