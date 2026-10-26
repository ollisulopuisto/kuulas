# Path-security implementation plan

Goal: fix confirmed request-derived path escapes and unsafe temporary-file opens
without restricting the user's intentional project-folder selection.

1. Trace all open path alerts to their request inputs using GitHub's Python SARIF.
2. Add regressions in `tests/test_path_security.py`, observe failures, then fix
   `new_project.py`, `record_take.py`, `record_session.py`, `series_library.py`,
   `package.py`, `bgjobs.py` and the recorder client's shared validator export.
3. Preserve the recorder-client import boundary and reuse the exclusive atomic
   JSON writer for editor plans. Retain existing English/Finnish error keys.
4. Run the affected subsystem tests, full pytest, Ruff, and document the distinction
   between confirmed bugs and intended folder/plug-in selection in the audit.
5. Integrator: include the verified PR fixes, update release documentation/version,
   push and tag, then verify both packaged-app selftests and publish the DMG.

Red: 25 security regressions failed; the extra editor-plan writer regression also
failed before its fix. Six additional job-ID regressions failed before validation
was added. Green: 132 focused security, recording, worker and catalog tests passed.

Final validation on the frozen implementation: 5,115 Python tests passed in
745.30 seconds; Ruff clean. The related PR fixes passed 5,083 Python tests,
3,513 UI tests and Biome 2.2.4; 18 design checks also passed with CRLF fixtures.
No CodeQL rule was suppressed and no alert was dismissed.
