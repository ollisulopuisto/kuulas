"""The recents list with metadata (the start screen): records, the folder size,
the recents file, and the start page's data."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from kuulas import desktop, messages
from kuulas.recent_projects import (
    folder_size,
    make_record,
    merge_record,
    normalize_record,
    update_record,
)


def folders(tmp_path, n):
    out = []
    for i in range(n):
        folder = tmp_path / f"P{i:02d}.kuulas"
        folder.mkdir()
        out.append(str(folder))
    return out


# -- pure records ---------------------------------------------------------------


def test_normalize_record_accepts_a_bare_path_from_the_old_file():
    assert normalize_record("/a/One.kuulas") == {"path": "/a/One.kuulas"}


def test_normalize_record_keeps_valid_metadata_and_drops_junk():
    raw = {"path": "/a/One", "opened_utc": "2026-10-19T10:00:00Z", "tracks": 3,
           "duration_s": 61.5, "size_bytes": 2048, "evil": 1}
    assert normalize_record(raw) == {
        "path": "/a/One", "opened_utc": "2026-10-19T10:00:00Z", "tracks": 3,
        "duration_s": 61.5, "size_bytes": 2048}
    bad = {"path": "/a/One", "tracks": -1, "duration_s": "long", "size_bytes": True,
           "opened_utc": 5}
    assert normalize_record(bad) == {"path": "/a/One"}


@pytest.mark.parametrize("item", [None, 3, [], {}, {"path": ""}, {"path": 4}, ""])
def test_normalize_record_rejects_what_has_no_path(item):
    assert normalize_record(item) is None


def test_merge_record_moves_to_front_and_keeps_old_metadata_it_is_not_given():
    old = [{"path": "/a/Two"}, {"path": "/a/One/", "tracks": 4, "size_bytes": 9}]
    got = merge_record(old, make_record("/a/One", "2026-10-19T10:00:00Z"))
    assert [r["path"] for r in got] == ["/a/One", "/a/Two"]
    assert got[0]["tracks"] == 4
    assert got[0]["opened_utc"] == "2026-10-19T10:00:00Z"
    assert old[1]["tracks"] == 4
    assert "opened_utc" not in old[1]


def test_merge_record_new_metadata_wins_and_the_list_is_cut():
    old = [{"path": f"/a/P{n}"} for n in range(5)]
    got = merge_record(old, make_record("/a/P3", "t", tracks=2), limit=3)
    assert got[0] == {"path": "/a/P3", "opened_utc": "t", "tracks": 2}
    assert len(got) == 3


def test_update_record_changes_metadata_without_reordering_or_touching_opened():
    old = [{"path": "/a/Two"}, {"path": "/a/One", "opened_utc": "t"}]
    got = update_record(old, "/a/One/", tracks=5, duration_s=12.0, size_bytes=None)
    assert [r["path"] for r in got] == ["/a/Two", "/a/One"]
    assert got[1] == {"path": "/a/One", "opened_utc": "t", "tracks": 5,
                      "duration_s": 12.0}


def test_update_record_ignores_a_project_not_in_the_list():
    old = [{"path": "/a/Two"}]
    assert update_record(old, "/a/Nope", tracks=1) == old


def test_folder_size_sums_the_files_and_never_follows_links(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / "a.bin").write_bytes(b"x" * 100)
    (root / "sub").mkdir()
    (root / "sub" / "b.bin").write_bytes(b"y" * 50)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"z" * 1000)
    (root / "link.bin").symlink_to(outside)
    assert folder_size(root) == 150


def test_folder_size_gives_up_on_a_huge_tree_instead_of_walking_it(tmp_path):
    for n in range(10):
        (tmp_path / f"f{n}").write_bytes(b"x")
    assert folder_size(tmp_path, max_entries=5) is None
    assert folder_size(tmp_path / "missing") is None


# -- the recents file -----------------------------------------------------------


def test_add_recent_stores_the_time_and_keeps_old_string_entries(tmp_path):
    file = tmp_path / "recent.json"
    a, b = folders(tmp_path, 2)
    file.write_text(json.dumps([a]), encoding="utf-8")  # the old format
    desktop.add_recent(file, b, now="2026-10-19T10:00:00Z")
    records = desktop.load_recent_records(file)
    assert [r["path"] for r in records] == [str(Path(b).resolve()), a]
    assert records[0]["opened_utc"] == "2026-10-19T10:00:00Z"
    assert "opened_utc" not in records[1]
    assert desktop.load_recents(file) == [str(Path(b).resolve()), a]


def test_load_recent_records_keeps_a_missing_folder_and_says_so(tmp_path):
    file = tmp_path / "recent.json"
    a, b = folders(tmp_path, 2)
    desktop.add_recent(file, a)
    desktop.add_recent(file, b)
    shutil.rmtree(a)
    records = desktop.load_recent_records(file)
    assert [(Path(r["path"]).name, r["exists"]) for r in records] == [
        (Path(b).name, True), (Path(a).name, False)]
    assert desktop.load_recents(file) == [str(Path(b).resolve())]


def test_a_later_open_does_not_forget_a_missing_project(tmp_path):
    file = tmp_path / "recent.json"
    a, b = folders(tmp_path, 2)
    desktop.add_recent(file, a)
    shutil.rmtree(a)
    desktop.add_recent(file, b)
    assert len(desktop.load_recent_records(file)) == 2


def test_set_recent_metadata_keeps_order_and_writes_nothing_in_the_project(tmp_path):
    file = tmp_path / "recent.json"
    a, b = folders(tmp_path, 2)
    (Path(a) / "project.sqlite").write_bytes(b"x" * 300)
    before = sorted(p.name for p in Path(a).iterdir())
    desktop.add_recent(file, a)
    desktop.add_recent(file, b)
    desktop.set_recent_metadata(file, a, tracks=3, duration_s=90.0)
    records = desktop.load_recent_records(file)
    assert [Path(r["path"]).name for r in records] == [Path(b).name, Path(a).name]
    assert records[1]["tracks"] == 3
    assert records[1]["size_bytes"] == 300
    assert sorted(p.name for p in Path(a).iterdir()) == before


# -- the start page ---------------------------------------------------------------


def test_launcher_embeds_the_rows_and_the_shared_model():
    page = desktop.launcher_html([
        {"path": "/x/Show.kuulas", "exists": True, "opened_utc": "2026-10-19T10:00:00Z",
         "tracks": 3, "duration_s": 61.0, "size_bytes": 2048},
        {"path": "/x/Gone.kuulas", "exists": False},
    ])
    assert 'id="recent-data"' in page
    assert "export function rowModel" in page


def test_launcher_data_cannot_close_the_script_tag():
    page = desktop.launcher_html([{"path": "/x/</script><b>.kuulas", "exists": True}])
    assert page.count("</script>") == page.count("<script")
    assert "<b>" not in page


def test_launcher_carries_the_shared_button_style_and_tokens():
    page = desktop.launcher_html([])
    assert ".button.primary" in page
    assert "--button-primary-bg" in page
    assert 'class="button primary"' in page


def test_launcher_script_parses_as_a_module(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    page = desktop.launcher_html([{"path": "/x/A.kuulas", "exists": True}])
    script = re.search(r'<script type="module">(.*)</script>', page, re.S).group(1)
    file = tmp_path / "launcher.mjs"
    file.write_text(script, encoding="utf-8")
    done = subprocess.run(  # noqa: S603 - node, and a file made just above
        [node, "--check", str(file)], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr


def test_launcher_labels_are_translated_in_both_languages():
    for lang in ("en", "fi"):
        messages.set_language(lang)
        try:
            page = desktop.launcher_html([])
        finally:
            messages.set_language("en")
        assert f'lang="{lang}"' in page
        assert "desktop.launcher" not in page


def test_launcher_still_takes_plain_paths():
    page = desktop.launcher_html(["/x/Old.kuulas"])
    assert "Old.kuulas" in page
