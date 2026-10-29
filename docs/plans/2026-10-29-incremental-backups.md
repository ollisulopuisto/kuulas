# Incremental History Backups Implementation Plan

**Goal:** Append only new backup content during an open session, yield to playback and editing, and leave a standalone full snapshot on close.

**Architecture:** Preserve existing standalone SQLite/xz backups and their restore path. Add a backup-only SQLite chunk repository, keyed by SHA-256 of bounded chunks of a consistent online SQLite snapshot, plus atomic `.kbackup` manifests. The first periodic backup and explicit Back up now stay standalone; later periodic backups share repository chunks. A manifest is published only after its chunks commit. Reconstruction verifies every chunk and the whole snapshot before the existing SQLite integrity check and restore safety copy. Project schema and media are unchanged.

**Tech Stack:** Python, SQLite online backup, SHA-256, zlib, pytest.

1. Write failing tests in `tests/test_incremental_backup.py`: deduplicated storage, all revisions restored, corrupt/missing repository data, cancellation, concurrent source writes and backup publication.
2. Implement `src/kuulas/incremental_backup.py`: bounded chunks, transactionally durable content rows, atomic manifests, validated reconstruction, conservative garbage collection and unique byte accounting. Validate with the new test file alone.
3. Write failing package tests for periodic incremental backup after a baseline, playback/input deferral, final full close snapshot, retention and legacy restore compatibility.
4. Integrate in `src/kuulas/package.py`: serialize backup creation and retention, use chunked cooperative online copy, defer timer work during interaction, stop/cancel background copies before final snapshot; preserve backup errors as logs on close, leaving history and media intact.
5. Extend `docs/FORMAT.md` with backup-only format, dependencies, recovery and retention. Update CLI help strings in both locales. Run complete pytest and Ruff gates. Do not prune history, change project schema or release metadata.

Risks: a `.kbackup` requires its sibling repository, so copying a single reference is insufficient; standalone manual and close snapshots remain portable. Retention must fail closed if any surviving manifest cannot prove its references. SQLite snapshot acquisition still reads the source database; only persistent backup storage and compression are incremental. A crash before manifest publication can leave harmless unreachable repository chunks, never an acknowledged partial backup. No thinning is authorized or needed.
