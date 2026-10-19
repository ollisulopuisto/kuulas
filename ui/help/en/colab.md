---
id: colab
title: Transcribing on Colab
applies-to: [transcript]
commands: [app.transcribe, app.transcribe_colab, app.colab_settings]
related: [transcript, track]
---
Transcription turns the speech into words you can read, search and cut by. It can run on this computer, or on Google Colab, which has a graphics card and is much faster on long recordings.

- On this computer: Track, Transcribe, On this computer, or {key:app.transcribe}. The audio stays here.
- On Colab: Track, Transcribe, On Colab (audio is uploaded to Google)…, or the second button in the empty transcript. **The audio is uploaded to Google.** The first time in a session kuulas says so and asks; "Do not ask again" remembers your answer. Nothing is uploaded until you press Upload and transcribe.
- It uses the focused track's recordings, or every speech track's when no track is focused. All of them go in one run.
- It runs in the background. The notice shows which recording the tool is on and its latest message; Cancel stops it. Your editing is not blocked.
- The words arrive as one undo step per recording, like a local transcript. A transcript you changed while Colab worked is never overwritten: the run fails with a message and you start it again.

The program kuulas runs is `colab-transcribe` from your podcast project, started with `uvx` by default. Check it under Track, Transcribe, Colab transcription settings…: the command, the folder it runs in, extra arguments, the model, the language, and whether the audio is sent directly instead of through Google Drive (the default). A missing program, a failed run and an unreadable result each give a message that says which.

Two recordings with the same file name (without the ending) cannot go in one run, because the result is matched by that name; transcribe them one at a time. See also [[transcript]].
