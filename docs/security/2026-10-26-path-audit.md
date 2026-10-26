# Path-access audit — 26 October 2026

GitHub's open alerts were downloaded from the repository's code-scanning API.
Python SARIF analysis 2025212304 supplied the complete request-to-file traces.
There were 55 open `py/path-injection` alerts. This review concerns those alerts;
other JavaScript, workflow-permission and error-disclosure alerts are separate.

## Confirmed gaps fixed

- Recording import accepted a request's take string before treating it as a file
  name (#47–48). The editor now uses the recorder client's shared name validator,
  rejects traversal/absolute/drive-qualified names, and refuses symlinked sidecars
  and editor plans. Invalid names give HTTP 400; an unavailable sidecar gives 404.
  Existing recorded files are never edited, removed or repaired by a bad request.
- Atomic JSON writes used a randomized but non-exclusive temporary file (#31–35,
  including `package.py:147`). A pre-existing temporary symlink could therefore
  truncate another file. `mkstemp` now creates the temporary file exclusively in
  the destination directory. Rename remains atomic; failures remove only this
  writer's temporary file. Editor plans reuse the same writer rather than opening
  a predictable `<plan>.tmp` path.
- New-project names now exclude Windows drive/alternate-stream punctuation and
  control characters as well as separators. The selected parent is canonicalized;
  a dangling project symlink counts as an existing destination, never as permission
  to create its target (#29–30, #64–65 and downstream project-root flows).
- Background-job IDs are checked before every path join and cleanup glob,
  including Windows separators and wildcard syntax. Job metadata, status, cancel
  and result paths refuse symlinks; listing jobs ignores symlinked metadata
  (#4–6 and the job-ID request paths examined during this audit).
- Series IDs require a full UUID-shaped match, including the end of the input.
  Series records are not read through symlinks, either individually or when
  listing the library (#49–51).

## Why many alerts share one input

The New project and New episode endpoints intentionally accept the user's
selected absolute parent folder. That folder becomes Session.package.path. CodeQL
then follows it into ordinary project operations: SQLite, manifests, locks,
backups, clipboard files, derived-media caches, background jobs and sync markers.
These are not dozens of independently supplied file names. Restricting all
projects to one hard-coded directory would break File > New project.

The checked rules at this boundary are: an existing absolute parent without `..`,
a single portable project-name component, a canonical parent, and no existing
project destination (including dangling symlinks). Browser requests also pass the
server's local Host/Origin checks. A process running as the user can still choose
any parent directory the user can access; this application is not a filesystem
sandbox.

Other intentional path inputs in this analysis:

- Open project (#8–10): an absolute existing `.kuulas` directory, no traversal,
  resolved before use. Only the fixed clipboard filename is read by browsing;
  clipboard symlinks are already rejected there.
- Local automixer plug-in paths (#7): explicit installed-file selection, checked
  for existence. An arbitrary local plug-in is executable code selected by the
  user; choosing one is not a request to read a project-relative file.
- Series records (#49–51): UUID-shaped leaf filenames in the configured library,
  now with full-input and symlink checks as described above.

No rules, alerts or analyses were suppressed or dismissed. Some warnings about
intentional user-selected roots may remain after the next CodeQL run. A passing
PR incremental scan alone does not establish that main's complete alert set is
clear. Review the next main analysis before claiming closure.

## Verification

Regression tests reproduce traversal-shaped requests, Windows drive/stream names,
symlinked records/plans, dangling project links, pre-existing temporary-file
collisions and JSON serialization failure. All 32 cases failed before their
corresponding fixes and passed afterwards. The initial 25-case group, additional
editor-plan writer case and six job-ID cases were run separately in the red phase.
The final focused run also covered background transcription and worker behavior,
record-take behavior and catalog parity: 132 tests passed.

These checks use synthetic files and fake engines. No real recordings, microphone,
playback device or user project was opened.

Final full-suite verification: 5,115 Python tests passed; Ruff clean. The UI
portability fixes separately passed all 3,513 Node tests and Biome 2.2.4. Existing
Starlette deprecation and native-binding exit diagnostics did not fail the tests.
