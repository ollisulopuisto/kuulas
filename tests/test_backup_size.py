"""Automatic backups that stay small (docs/FORMAT.md "Backups"): xz-compressed,
old uncompressed ones compressed in the background, a size budget on top of the
count rules, no backup without a change or without disk room, a restore that reads
either form, and the project's size by part in the statistics."""

import hashlib
import json
import logging
import lzma
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kuulas import cli, messages, ops, package, priority, project_stats


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


def name(t: datetime, xz: bool = False) -> str:
    return f"auto-{t.strftime('%Y%m%dT%H%M%SZ')}.sqlite" + (".xz" if xz else "")


def edited(tmp_path: Path, gain: float = -1.0) -> package.Package:
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.history.commit("edit", ops.set_master(pkg.history.state, gain))
    return pkg


def autos(pkg_or_folder) -> list[str]:
    folder = getattr(pkg_or_folder, "path", pkg_or_folder)
    return sorted(p.name for p in (Path(folder) / "backups").iterdir()
                  if p.name.startswith("auto-"))


def node_count(db: Path) -> int:
    copy = sqlite3.connect(db)
    try:
        return copy.execute("select count(*) from nodes").fetchone()[0]
    finally:
        copy.close()


# -- (1) compressed backups ----------------------------------------------------------


def test_a_backup_ends_up_as_one_verified_xz_file(tmp_path):
    pkg = edited(tmp_path)
    made = pkg.backup()
    pkg.wait_compressed()
    (only,) = autos(pkg)
    assert only == made.name + ".xz"
    restored = package.read_backup(pkg.path / "backups" / only, tmp_path / "check.sqlite")
    assert node_count(restored) == 2
    pkg.close()


def test_compression_runs_on_a_gated_background_thread(tmp_path, monkeypatch):
    seen = []
    real = priority.checkpoint

    def spy(cancel=None, **kw):
        seen.append((threading.current_thread().name, priority.is_background()))
        return real(cancel, **kw)

    monkeypatch.setattr(priority, "checkpoint", spy)
    pkg = edited(tmp_path)
    pkg.backup()
    pkg.wait_compressed()
    assert seen
    assert all(bg for _name, bg in seen)
    assert all(n != threading.current_thread().name for n, _bg in seen)
    pkg.close()


def test_a_failed_compression_keeps_the_uncompressed_backup(tmp_path, monkeypatch):
    pkg = edited(tmp_path)

    def bad(_path, _cancel=None):
        return "not the same"

    monkeypatch.setattr(package, "_xz_digest", bad)
    made = pkg.backup()
    pkg.wait_compressed()
    assert autos(pkg) == [made.name]
    assert not list((pkg.path / "backups").glob("*.partial"))
    pkg.close()


# -- (2) old uncompressed backups ------------------------------------------------------


def test_old_uncompressed_backups_are_compressed_on_open_and_nothing_else(tmp_path):
    pkg = edited(tmp_path)
    folder = pkg.path
    pkg.close()
    backups = folder / "backups"
    # Closing now creates the final full snapshot as well. All standalone
    # copies, including that snapshot, must be compressed on the next open.
    old = list(backups.glob("auto-*.sqlite"))
    for minutes in (30, 20):
        t = datetime.now(UTC) - timedelta(minutes=minutes)
        old.append(package.backup_to(folder / "project.sqlite", backups / name(t)))
    digests = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in old}
    pre = backups / "pre-migration-v0-20260101T000000Z.sqlite"
    pre.write_bytes(b"pre-migration copy")
    other = backups / "notes.txt"
    other.write_bytes(b"mine")
    stamps = {p: p.stat().st_mtime_ns for p in (pre, other)}

    pkg = package.open_package(folder)
    pkg.start()
    pkg.wait_compressed()
    pkg.close()
    assert autos(folder) == sorted(n + ".xz" for n in digests)
    for raw_name, digest in digests.items():
        data = lzma.decompress((backups / (raw_name + ".xz")).read_bytes())
        assert hashlib.sha256(data).hexdigest() == digest
    assert pre.read_bytes() == b"pre-migration copy"
    assert other.read_bytes() == b"mine"
    assert {p: p.stat().st_mtime_ns for p in (pre, other)} == stamps


def test_a_read_only_open_compresses_nothing(tmp_path, monkeypatch):
    pkg = edited(tmp_path)
    raw = package.backup_to(pkg.db_path, pkg.path / "backups" / name(datetime.now(UTC)))
    monkeypatch.setattr(package, "_hostname", lambda: "other-mac")
    other = package.open_package(pkg.path)
    assert other.read_only
    other.start()
    other.wait_compressed()
    other.close()
    assert autos(pkg) == [raw.name]
    pkg.close()


# -- (3) retention: both forms and the budget -----------------------------------------


def test_retention_counts_compressed_and_uncompressed_alike(tmp_path):
    folder = tmp_path / "backups"
    folder.mkdir()
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    times = [now - timedelta(minutes=10 * i) for i in range(20)]
    for i, t in enumerate(times):
        (folder / name(t, xz=i % 2 == 0)).write_bytes(b"x")
    package.prune_backups(folder, now=now, tz=UTC)
    kept = sorted(folder.iterdir(), reverse=True)
    assert len(kept) == package.KEEP_RECENT
    assert kept[0].name == name(times[0], xz=True)


def write_size(path: Path, size: int) -> None:
    with path.open("wb") as f:
        f.truncate(size)


def test_the_budget_drops_oldest_first_but_keeps_the_newest_two_and_three_days(
        tmp_path, caplog):
    folder = tmp_path / "backups"
    folder.mkdir()
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    today = [now - timedelta(minutes=10 * i) for i in range(4)]
    days = [now - timedelta(days=d) for d in range(1, 6)]
    for t in today + days:
        write_size(folder / name(t, xz=True), 10_000_000)
    caplog.set_level(logging.INFO, logger="kuulas.package")
    removed = package.prune_backups(folder, now=now, tz=UTC, budget=45_000_000)
    kept = {p.name for p in folder.iterdir()}
    # 9 backups of 10 MB, 45 MB allowed: the oldest go first (days 5, 4, 3 back)
    # and then today's older ones, never the newest two nor yesterday's or the
    # day before's newest.
    assert kept == {name(t, xz=True) for t in (*today[:2], days[0], days[1])}
    assert len(removed) == 5
    assert "10.0 MB" in caplog.text
    assert name(days[4], xz=True) in caplog.text


def test_the_protected_backups_stay_even_over_the_budget(tmp_path, caplog):
    folder = tmp_path / "backups"
    folder.mkdir()
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    times = [now, now - timedelta(minutes=10), now - timedelta(days=1),
             now - timedelta(days=2), now - timedelta(days=3)]
    for t in times:
        write_size(folder / name(t, xz=True), 10_000_000)
    caplog.set_level(logging.INFO, logger="kuulas.package")
    package.prune_backups(folder, now=now, tz=UTC, budget=1)
    assert {p.name for p in folder.iterdir()} == {name(t, xz=True) for t in times[:4]}
    assert "over the budget" in caplog.text


def test_budget_zero_or_none_is_unlimited(tmp_path):
    folder = tmp_path / "backups"
    folder.mkdir()
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    times = [now - timedelta(minutes=10 * i) for i in range(5)]
    for t in times:
        write_size(folder / name(t, xz=True), 10_000_000)
    assert package.prune_backups(folder, now=now, tz=UTC, budget=0) == []
    assert package.prune_backups(folder, now=now, tz=UTC) == []
    assert len(list(folder.iterdir())) == 5


def test_the_budget_comes_from_settings_json(tmp_path):
    settings = messages.settings_file()
    assert package.backup_budget_bytes() == 300_000_000
    settings.write_text(json.dumps({"backup_budget_mb": 50}))
    assert package.backup_budget_bytes() == 50_000_000
    settings.write_text(json.dumps({"backup_budget_mb": 0}))
    assert package.backup_budget_bytes() == 0
    for bad in (-5, "lots", None):
        settings.write_text(json.dumps({"backup_budget_mb": bad}))
        assert package.backup_budget_bytes() == 300_000_000


# -- (4) skips ---------------------------------------------------------------------------


def test_no_new_backup_when_nothing_changed(tmp_path):
    pkg = edited(tmp_path)
    first = pkg.backup(datetime.now(UTC))
    pkg.wait_compressed()
    again = pkg.backup(datetime.now(UTC) + timedelta(minutes=1))
    pkg.wait_compressed()
    assert again.name.startswith(first.name)
    assert len(autos(pkg)) == 1
    pkg.history.commit("edit", ops.set_master(pkg.history.state, -2.0))
    third = pkg.backup(datetime.now(UTC) + timedelta(minutes=2))
    pkg.wait_compressed()
    assert third != again
    assert len(autos(pkg)) == 2
    pkg.close()


def test_a_new_session_never_takes_an_old_backup_for_its_own(tmp_path):
    # An earlier session's backup may predate edits a crash left unbacked-up.
    pkg = edited(tmp_path)
    pkg.backup(datetime.now(UTC))
    pkg.wait_compressed()
    pkg.close()
    again = package.open_package(pkg.path)
    made = again.backup(datetime.now(UTC) + timedelta(minutes=1))
    again.wait_compressed()
    assert made is not None
    assert len(autos(again)) == 2
    again.close()


def test_no_backup_and_no_error_when_the_disk_is_nearly_full(tmp_path, monkeypatch,
                                                              caplog):
    pkg = edited(tmp_path)
    size = pkg.db_path.stat().st_size

    class Usage:
        total = used = 0
        free = size  # below twice the database

    monkeypatch.setattr(package.shutil, "disk_usage", lambda _p: Usage)
    caplog.set_level(logging.INFO, logger="kuulas.package")
    assert pkg.backup() is None
    assert pkg.tick(now=datetime.now(UTC) + timedelta(minutes=11)) is None
    assert autos(pkg) == []
    assert "disk" in caplog.text.lower()
    pkg.close()


# -- restore --------------------------------------------------------------------------


def test_restore_reads_a_compressed_backup_and_keeps_a_safety_copy(tmp_path):
    pkg = edited(tmp_path, gain=-1.0)
    made = pkg.backup()
    pkg.wait_compressed()
    pkg.history.commit("edit", ops.set_master(pkg.history.state, -7.0))
    folder = pkg.path
    pkg.close()
    assert len(autos(folder)) == 2  # earlier edit plus the final close snapshot
    backup = made.name + ".xz"
    assert backup in autos(folder)
    assert backup.endswith(".xz")
    assert made is not None
    safety = package.restore_backup(folder, backup)
    assert safety.name.startswith("pre-restore-")
    assert node_count(safety) == 3
    again = package.open_package(folder)
    assert again.history.state.master_gain_db == -1.0
    again.close()
    assert cli.main(["info", str(folder)]) == 0


def test_restore_from_the_command_line(tmp_path, capsys):
    pkg = edited(tmp_path, gain=-2.0)
    made = pkg.backup()
    pkg.wait_compressed()
    pkg.history.commit("edit", ops.set_master(pkg.history.state, -9.0))
    pkg.close()
    assert len(autos(pkg)) == 2  # final snapshot must not replace the older one
    backup = made.name + ".xz"
    assert backup in autos(pkg)
    assert cli.main(["restore-backup", str(pkg.path), backup]) == 0
    assert "pre-restore-" in capsys.readouterr().out
    again = package.open_package(pkg.path)
    assert again.history.state.master_gain_db == -2.0
    again.close()


def test_restore_refuses_while_the_project_is_open(tmp_path):
    pkg = edited(tmp_path)
    pkg.backup()
    pkg.wait_compressed()
    (backup,) = autos(pkg)
    with pytest.raises(package.PackageError):
        package.restore_backup(pkg.path, backup)
    pkg.close()


def test_a_damaged_backup_is_refused_and_the_live_file_is_untouched(tmp_path):
    pkg = edited(tmp_path)
    folder = pkg.path
    pkg.close()
    bad = folder / "backups" / name(datetime.now(UTC), xz=True)
    bad.write_bytes(lzma.compress(b"not a database at all" * 100)[:-10])
    before = (folder / "project.sqlite").read_bytes()
    with pytest.raises(package.PackageError):
        package.restore_backup(folder, bad.name)
    assert (folder / "project.sqlite").read_bytes() == before
    assert not list(folder.glob("*.partial"))
    assert not list((folder / "backups").glob("pre-restore-*"))


# -- (5) sizes -----------------------------------------------------------------------


def test_info_counts_backups_once_per_stamp_and_their_bytes(tmp_path):
    pkg = edited(tmp_path)
    pkg.backup()
    pkg.wait_compressed()
    pkg.close()
    data = package.info(pkg.path)
    assert data["backups"] == 1
    assert data["sizes"]["backups"] > 0
    assert "recordings" in data["sizes"]


def test_stats_break_the_project_size_down_with_a_hint_each(tmp_path):
    pkg = edited(tmp_path)
    pkg.backup()
    pkg.wait_compressed()
    (pkg.path / "recordings" / "take.wav").write_bytes(b"r" * 1000)
    (pkg.path / "caches" / "peaks" / "x.bin").write_bytes(b"c" * 500)
    stats = project_stats.gather(pkg.history, pkg.path)
    size = stats["size"]
    assert size["backups_count"] == 1
    assert size["backups_bytes"] > 0
    assert size["history_bytes"] >= pkg.db_path.stat().st_size
    assert size["recordings_folder_bytes"] == 1000
    assert size["caches_bytes"] == 500
    assert "media_bytes" in size
    (group,) = [g for g in project_stats.groups(stats) if g["title"] == "Size"]
    labels = [row[0] for row in group["rows"]]
    assert any("Backups" in label for label in labels)
    backups_row = next(row for row in group["rows"] if "Backups" in row[0])
    assert backups_row[2] == "Copies of the history, kept for safety."
    assert all(len(row) == 3 and row[2] for row in group["rows"])
    # The text keeps one line per number.
    assert "Backups" in project_stats.to_text(stats)
    pkg.close()
