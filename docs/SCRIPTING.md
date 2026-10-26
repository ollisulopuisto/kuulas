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

## Not built yet

`kuulas ctl` (driving a window that is already open), `kuulas run <script>`, and an MCP server
that wraps the catalogue (list commands, call a command, read the transcript and the project),
read-only by default. The catalogue is the part they would all stand on.
