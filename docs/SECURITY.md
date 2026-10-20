# kuulas: security goals and practices

Written 2026-10-19 for the person (or agent) doing a security review or hardening pass. It is the design
reference for WP59 (hardening: fuzzing and a security review) in `docs/PLAN.md`. "Built" means read in the code
on `main` that day; "to verify" means nobody has checked it; "open" means known and not done.

## 1. What kuulas is, for a security reader

A single-user desktop editor for spoken-word audio, run locally by its owner. A Python process serves a browser
UI on `127.0.0.1` (FastAPI, plain ES modules), shown in a pywebview window; a separate recorder process captures
audio; background jobs run external tools. There is no kuulas server on the internet, no accounts, no telemetry.
The repo is **public** (since 2026-10-19), and unsigned `.dmg` releases are published from CI.

## 2. Assets, in priority order

1. **Recorded material.** It cannot be re-recorded. Never lose it, never overwrite it (PLAN ground rule 17).
2. **The user's edits and project files** (`*.kuulas`, SQLite history), often in a Dropbox-synced folder.
3. **Private audio and transcripts.** Household and interview audio stays on the machine unless the user
   explicitly sends it (Colab transcription asks first; Google Drive is never used for audio).
4. **Credentials the user holds** (the Colab/Google token, API keys): kuulas must not read them into logs, chat
   or the UI; they stay in the owning tool's own store.
5. **The machine** (no arbitrary file write, no code execution from content).

## 3. Trust boundaries (who can send kuulas something hostile)

| Boundary | Hostile input |
|---|---|
| Any web page the user visits | requests to the local server (CSRF, DNS rebinding) |
| Imported media and Hindenburg `.nhsx` sessions | malformed audio/video, XML, huge or crafted files; file names |
| A `.kuulas` project from someone else ("Send a copy") | crafted SQLite/JSON, paths, symlinks, huge fields |
| Take sidecars and job files (`*.take.json`, `jobs/*.json`) | oversized or wrong-typed JSON |
| The recorder socket and worker processes | any local process on the same account |
| External tools kuulas runs (`ffmpeg`, `uvx colab-transcribe`, `automixer`) | their output lines; the command itself comes from settings |
| The desktop bridge (pywebview `js_api`) | whatever script runs in the page |
| Pasted/dropped paths and text | traversal, NUL, leading `-`, very long strings |
| The supply chain | PyPI/npm packages, the `speechmix` and `nhsx` path dependencies, the podcast repo, GitHub Actions |

## 4. Goals

1. A web page on another origin cannot read or change anything through the local server.
2. Opening, importing or receiving untrusted content cannot write outside the project, run code, or hang the app.
3. No operation can delete or truncate a recorded file as a side effect (undo, restore, cleanup, failed write).
4. Secrets never appear in logs, notices, command lines, the repo or chat.
5. External commands are run without a shell, with argument lists, resolved to absolute paths, with a bounded
   environment and bounded output.
6. A crash, a full disk or a killed process leaves valid files and a recoverable project.
7. Builds are reproducible and a release can be traced to a commit; the repo holds no personal data or secrets.

## 5. Practices (rules for everyone writing code here)

- **Validate at every boundary**: type, length, range, allowed characters; reject, do not "fix up" silently.
  Cap sizes before parsing (JSON files, request bodies, strings). Never use a path from a request or a file
  without checking it is inside the folder it is meant for (`..`, symlinks, absolute paths, NUL, `~`).
- **Subprocesses**: `subprocess` with a list, never `shell=True`; user text never becomes a flag (prefix `./` or
  use `--`); resolve the program (`toolpath.resolve`); set `start_new_session` and a timeout or cancel path;
  strip terminal escape codes from output before showing it (`automix.clean_output_line`).
- **Files**: write atomically (`caches.write_atomic`, rename); never write inside a user's project from a
  read-only tool (the spike scripts copy metadata first); never `resolve()` away the path the user chose.
- **The local server**: bind `127.0.0.1` only (`cli.bind_local`); keep the Host and Origin checks; no
  permissive CORS; state-changing calls are never GET.
- **Secrets**: never read, log or print a token's content; tests use fake tokens (`KUULAS_COLAB_TOKEN`); no
  secrets on command lines or in `argv`.
- **Locks and slow work**: no session lock held during slow work (a hostile file must not freeze the editor).
- **Errors** are message keys with parameters, not raw exception text with paths or content.
- **Dependencies**: pin exact versions (`uv.lock`); prefer the standard library for small jobs; review any new
  dependency's maintainers and install scripts; GitHub Actions pinned to a major version at least, least
  privilege `permissions:` per workflow.
- **Public repo hygiene**: no real names, emails, tokens, audio, transcripts or project files in commits or
  fixtures; fixtures are synthetic. Scan before making a branch public.
- **Tests**: every hardening fix has a failing test first; fuzz tests assert "clean 4xx or a refusal, never a
  crash, never a write outside the project".

## 6. What is built (verified in code, 2026-10-19)

- Server bound to `127.0.0.1` on an owned socket (`bind_local`); `Host` must be loopback or `testserver`, `Origin`
  (when present) must be a loopback page, else 400/403 (`server.py`, `tests/test_origin_check.py`,
  `tests/test_fuzz_hardening.py`).
- `locate_media` validates its folder; `Bridge.open_project` rejects empty/NUL/non-string; `reveal_command`
  guards a leading `-`; `TakePlan` JSON is capped (256 KB file, 1024-char strings, type checks).
- Media identified by SHA-256; recorded files are never deleted (`protected_files.py` logic exists; wiring of
  every delete path to it is open, see below).
- External commands run without a shell; tool paths resolved (`toolpath.py`); output cleaned of escape codes.
- Colab sign-in keeps the code out of logs and storage; the token file is only checked for existence/shape.
- Content-hash caches, atomic writes, per-host locks, crash-safe progressive WAV with sidecars.

## 7. Open items, in the order to do them (a review checklist)

1. **Fuzz the recorder** (after multi-track is confirmed on real hardware): protocol messages on the Unix socket,
   sidecar/journal parsing, kill and disk-full at random points; assert every flushed audio frame survives.
2. **Recorder socket permissions** (to verify): who can connect to `rec.sock`; the socket directory should be
   `0700` and the socket `0600`; refuse peers of another uid.
3. **Fuzz the importers**: `ffmpeg`/`soundfile` decode paths with truncated/huge/odd files (timeouts exist: probe
   20 s, decode stall 120 s; check memory and disk limits), `.nhsx` XML (billion-laughs/entity expansion,
   huge attributes; check the parser is `defusedxml`-safe or has entity expansion off), media file names.
4. **Project files from strangers** ("Send a copy", Locate media): SQLite with hostile content, JSON `extra`
   fields, symlinks inside a `.kuulas` folder, paths in `manifest.json`; opening must never follow a path out
   of the project.
5. **Wire `protected_files.check_delete` into every delete/overwrite path** (export overwrite, cache cleanup,
   "clear old clipboard entries", restore) and add a test that grep-finds raw `unlink`/`rmtree` calls.
6. **Desktop bridge**: list each `Bridge` method callable from page JS (`copy_text`, `reveal_export`,
   `open_project`, `choose_*`, `dropped`, `minimise`, `close_project`...), restrict to what the page needs, and
   check that page content that comes from a transcript or a media name can never be executed as script
   (the UI uses `textContent`; audit `innerHTML`/`insertAdjacentHTML`).
5b. **XSS in the UI**: grep `ui/` for `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval`, `new Function`, and
    for user-controlled strings placed in attributes; transcripts, track names and marker text are attacker
    controlled if a project comes from someone else.
6. **Settings that name a command** (`colab.json`, `automixer.json`: `command`, `cwd`, `extra_args`): anyone who
   can write these files can run code as the user; check file permissions and that a project file can never
   set them (they live per user, not in the project).
7. **`uvx colab-transcribe` fetches code from git at run time**: a trust decision; document it, pin a commit,
   and show the command before the first run.
8. **WebSocket live channel**: Origin check applies? (`ws.headers` is used for language; verify the upgrade is
   covered by the same Host/Origin rule.)
9. **Request limits**: body size limits, upload sizes, the number of concurrent jobs, rate of expensive
   endpoints (a page on the same machine can still spam them).
10. **Dependencies and CI**: run `pip-audit` / `npm audit` (the UI has no runtime npm deps; Biome is dev only);
    pin `actions/*` to commit SHAs; `dmg.yml` has `contents: write` (release step): keep it on tag/dispatch only,
    never on pull requests from forks.
11. **Release integrity**: the dmg is unsigned/not notarised (users run `xattr`). Plan: Developer ID signing and
    notarisation (needs an Apple account); publish `SHA256.txt` (done) and verify it in `docs/TESTERS.md`.
12. **Privacy**: logs (`~/Library/Logs/Kuulas`) may contain paths and file names; review what is logged at INFO;
    make "copy diagnostics" redact home paths.
13. **Git history scan** for secrets and personal data now that the repo is public (current files were scanned
    on 2026-10-19; history was not).

## 8. How to test, for the reviewer

- `uv run pytest -q tests/test_fuzz_hardening.py tests/test_origin_check.py tests/test_import_order.py` (existing
  security tests), then add yours next to them.
- Local server: `curl -H "Host: evil.example" http://127.0.0.1:PORT/api/state` must be 400;
  `curl -H "Origin: https://evil.example" ...` must be 403.
- Use synthetic projects and fake media only (see `tests/` helpers); never test on real household audio.
- Report findings as a failing test plus a one-paragraph description; fix in a separate commit.

## 9. Reporting

This is a one-owner project: security findings go to the owner directly (not to a public issue) until fixed.
