# Scripting kuulas: for programs and agents

Written 2026-10-26 (WP53). kuulas is made so that a program can do what a person does in the
editor: list the commands, read the transcript, change the session. A person then opens the
session and adjusts it. Nothing here controls the window (selection, zoom, playback follow);
that is on purpose.

## The idea

- **Every edit is a command with a name and JSON arguments.** The editor holds no editing
  logic of its own beyond building the arguments, so a script can do anything a click can.
- **Every command that changes the edit is one undo step.** Whatever a script does, a person
  can undo it, one command at a time.
- **The catalogue says what exists.** A program does not need to know the commands in advance.
- **Positions are integer frames** at the project's rate (usually 48000), never seconds. Word
  times from the transcript are frames too.

## The catalogue

Every edit and every session command, with its route, arguments, a one-line summary and
whether it makes an undo step:

```python
from kuulas import command_catalog

for entry in command_catalog.catalog():
    print(entry["name"], entry["via"], entry["undo_step"], entry["summary"])
```

With a window or server running, the same list is `GET /api/commands`. An entry looks like:

```json
{"name": "split_clip", "via": "/api/edit", "undo_step": true,
 "summary": "Split a clip in two at frame ``at``.",
 "args": [{"name": "clip_id", "type": "str", "required": true},
          {"name": "at", "type": "int", "required": true},
          {"name": "new_id", "type": "str | None", "required": false, "default": null}]}
```

`via` says how to call it: `/api/edit` for an edit (`{"op": name, "args": {...}}`) and
`/api/command` for a session command (`{"name": name, "args": {...}}`). The catalogue is
checked by `tests/test_command_catalog.py`: a command that is missing from it fails the tests.

## Two ways to run a script

### Headless: no server, no window

```python
from kuulas.session import Session

session = Session("Episode.kuulas")
try:
    words = session.heard_words()        # [{"w": "um", "s": 96000, "e": 120000, ...}, ...]
    session.command("cut_words", {"indices": [4]})                    # a session command
    session.edit("set_track", {"track_id": "t1", "gain_db": -3.0})    # an edit
    session.undo()                                                    # takes the edit back
finally:
    session.close()
```

`Session(folder)` opens the project folder and `close()` releases it. A project that is open
in a window is **read-only** for a second session: `session.read_only` is true, and an edit
raises an error that says so (`error.history.read_only`). A script can read, but it must wait
for the window to close before it changes anything.

### Over HTTP: while the editor runs

Start the server for a project:

```
uv run kuulas open Episode.kuulas --no-browser
```

It prints the address (a local one, `127.0.0.1`). Then:

| Route | What it does |
|---|---|
| `GET /api/commands` | the catalogue |
| `GET /api/state` | the whole project |
| `GET /api/words` | the words someone hears (the same list `heard_words()` gives) |
| `POST /api/edit` | `{"op": name, "args": {...}}`: an edit, one undo step |
| `POST /api/command` | `{"name": name, "args": {...}}`: a session command |
| `POST /api/undo`, `POST /api/redo` | one step back or forward |

The server answers only to programs on the same machine. A web page on another site is
refused (the `Origin` check); a script, `curl` or a test, which send no `Origin`, are not.

## A worked example: remove the filler words

[`scripts/examples/remove_fillers.py`](../scripts/examples/remove_fillers.py) opens a project,
finds the filler words in the transcript and removes them with `cut_words`, the command the
transcript's X key runs. No LLM and no judgement are involved: it is a list of words and a
loop.

```
uv run python scripts/examples/remove_fillers.py Episode.kuulas --dry-run
uv run python scripts/examples/remove_fillers.py Episode.kuulas
```

Two things it shows that are easy to get wrong:

- `cut_words` removes the **whole stretch** from its first to its last word. Words that are not
  next to each other cannot go in one call, or the words between them go too. The example cuts
  each run of side-by-side fillers on its own.
- The positions in `cut_words` are positions in `heard_words()`, which change after every cut.
  The example reads the words again each time.

`tests/test_example_remove_fillers.py` runs it on a small synthetic project, so the example
cannot stop working without a test failing.

## For an agent

1. Read the catalogue to see what exists.
2. Read the state and the words, then make the changes with edits and commands. Keep to the
   catalogue's argument names and types.
3. Recorded material is never to be lost (PLAN.md ground rule 17): a script must not delete a
   recording or an imported file, and undoing an edit never touches the files.
4. Say what you did. The person opens the session, sees the steps in History, and undoes or
   adjusts what they do not want.

## MCP server

Kuulas also exposes the same project and command surface over the Model Context Protocol.
Install the optional integration and start it for one project:

```sh
uv run --extra agent kuulas-mcp "/path/to/Episode.kuulas"
```

For an MCP host that accepts a JSON server configuration, the read-only setup is:

```json
{
  "mcpServers": {
    "kuulas": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/kuulas", "--extra", "agent",
               "kuulas-mcp", "/path/to/Episode.kuulas"]
    }
  }
}
```

To enable changes, add `--allow-edits` after the project path. This is a launch-time opt-in;
each transcription or edit call must still pass `confirm=true`. Candidate application has its
own `confirm=true` gate. A project already open in Kuulas is exposed read-only, regardless of
the launch option. No tool can run shell commands or delete source recordings.

The tools are `project_summary`, `list_media`, `read_transcript`, `list_jobs`, `list_commands`,
`list_candidates`, `preview_candidate`, `transcribe_media`, `call_command` and
`apply_candidate`. A typical agent workflow is:

1. Read the summary and media list, then select the media to process.
2. Call `transcribe_media` with `confirm=true`. Local transcription uses the selected local
   engine (Whisper by default or Orukeet); `backend="colab"` sends the selected audio to Google
   and requires Kuulas to be signed in to Colab first.
3. Poll `list_jobs`, then read `read_transcript` after jobs complete.
4. Call `list_commands` to discover candidate detection and transcript editing commands.
   Run candidate detection with `call_command`, inspect `list_candidates` and
   `preview_candidate`, then apply only the reviewed candidates with `apply_candidate` and
   `confirm=true`.

Transcript timestamps and editing positions use integer project frames. The MCP server does not
make editorial decisions itself: the connected agent chooses which catalogued operations to
call, while Kuulas validates and commits each requested operation through `Session` history.

## Driving an open project

`kuulas ctl` can inspect and drive a project already open in a Kuulas window. Its loopback
server publishes a private per-process token in the project's `ctl.json`; the CLI reads it
and sends the token with each request. Examples:

```sh
uv run kuulas ctl Episode.kuulas state
uv run kuulas ctl Episode.kuulas commands
uv run kuulas ctl Episode.kuulas set_track --args '{"track_id":"...","gain_db":-3}'
uv run kuulas ctl Episode.kuulas transport --args '{"action":"stop"}'
```

`state`, `words`, `commands`, `stats`, `transport`, `undo` and `redo` are built-in
actions. Other actions are resolved against the running server's command catalog. The
client prints JSON so an agent can inspect the result and choose its next action. Projects
must already be open in the desktop app or through `kuulas open`.

The standalone MCP server (`kuulas mcp <project>`) is a separate headless workflow. It
opens a session itself and offers the same catalog and transcript tools documented above.
`kuulas run <script>` is not built yet.
