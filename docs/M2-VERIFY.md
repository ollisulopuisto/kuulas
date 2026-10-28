# M2 verification: what the owner needs to try

M2 is "A usable editor": transcript, mouse editing, history panel, fast listening, FX layers. Its items count as
built and merged (ROADMAP "Milestones"; most are "partly": the core works, some UI or edge is missing); this list
is what the owner still has to confirm in the installed app. Same rules as `docs/M1-VERIFY.md`: report a failure to
the coordinator (it goes into `docs/BUGS.md`; only the owner closes items), fill in the last column as you go.
Use the latest dmg from GitHub Releases and a copy of a real episode (two or three speech tracks, 10 to 60 minutes),
not the original. Transcription needs the Colab or local setup of the Preferences dialog; skip rows 9-11 if it is not
set up and say so.

| # | Try | Pass when | WP | Owner result |
|---|---|---|---|---|
| 1 | Make five edits (split, move, trim, gain), open the History tab (Cmd+2); click an older step; make a new edit; Cmd+Shift+S to save a named version | steps are listed, clicking one shows that state, the state you leave stays reachable (Enter on a picked step restores it as a new step), the named version appears as "Saved HH.MM" | 8 |  |
| 2 | Hold Shift+L and Shift+J; press `.` for fast playback and `,` / Alt+`.` to change the speed; Alt+0 to reset; also set 1.5x and 2x and press Space to stop mid-word | slow listening plays only while held; fast listening keeps the pitch; stop is instant and the cursor does not jump back; the speed is remembered after a restart | 26 |  |
| 3 | Mark in and out (I, O) and press Cmd+U; select two clips and press Cmd+U | the range or the selection loops cleanly, no click at the loop point; Cmd+U again stops | 50 |  |
| 4 | Look at a clip whose clip gain you changed, and at a loud peak | the waveform grows or shrinks with the gain; clipping shows in a warning colour | 57 |  |
| 5 | Move a clip near another track's clip with the mouse | a ghost shows where it will land, guide lines appear at clip edges and the cursor; the clip snaps where the hint says | 63 |  |
| 6 | Zoom by dragging in the ruler (and by the keys `+`, `-`, `0`, `F`); change the display scale in Preferences | zoom is smooth, the view keeps the cursor in sight, the scale change is applied and remembered | 52 |  |
| 7 | Run Auto-Silence (Alt+Cmd+P) on the speech tracks; play; then "Open this stretch" on one gated stretch | each microphone is silent where its owner is not talking; the clips are not cut; opening one stretch brings the sound back; one undo step undoes it | 44 |  |
| 8 | Duck the microphones (Cmd+L), then drag a ducking point on a track | the track dips while another speaker talks; the points can be dragged; undo removes it | 22 |  |
| 9 | Transcribe a track (Shift+Cmd+I, or the Colab route) and wait | a background job shows progress and can be cancelled or left running while you edit; closing the project does not stop it; words appear when done | 9, 78, 79 |  |
| 10 | Open the Transcript tab; press Cmd+F and type a word; click a word; select words and delete them | the match is found and the cursor goes there; clicking a word moves the play cursor; deleting words cuts those stretches in the audio (one undo step) | 7 |  |
| 11 | Look at the clips on the timeline at a high zoom | the words of the transcript show inside the clips and follow the clip when it moves | 69 |  |
| 12 | Tracks with several people (a Zoom file): set the track role, name the speakers in the Inspector | the speakers and the tags are remembered; a many-speaker track is never ducked per microphone | 41, 22 |  |
| 13 | Loudness: look at the track meters and the target of a track (Inspector); run Match loudness on selected clips | the numbers are plausible (speech about -19, music about -23 LUFS as the default targets); Match loudness sets clip gains so the clips are equally loud | 49 |  |
| 14 | Open Statistics (File or Help) on a long session | runtime, number of edits, clips and the size breakdown show; no window freezes | 70 |  |
| 15 | Press F1 on a dialog; Cmd+Shift+K and type "mute"; open Help > Keys | contextual help opens for what you are on; command search finds the command with its menu and key | 48 |  |
| 16 | Install from the dmg on a second Mac (or a clean user): the dmg is unsigned, run `xattr -dr com.apple.quarantine` on the app | the app starts without a terminal command after that; a project opens; the recorder and the transcription ask for what they need | 55 |  |

Not part of this list (they belong to later milestones): cut candidates, versions of an edit, review, roles in the
export, takes, recording, the automixer.
