"""The gate in the project format (WP44, docs/FORMAT.md): version 3, and an
old reader refuses a project that contains a gate."""

import json
import time

import pytest

from kuulas import ops, package
from kuulas.history import edit_blob
from kuulas.model import Media, Project
from kuulas.session import Session

RATE = 48000


def manifest(folder):
    return json.loads((folder / "manifest.json").read_text())


def with_track(pkg):
    h = pkg.history
    h.commit("track", ops.add_track(h.state, track_id="t", name="A"))


def test_format_version_is_three_and_min_reader_stays_one_without_a_gate(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    with_track(pkg)
    pkg.close()
    m = manifest(tmp_path / "A.kuulas")
    assert (m["version"], m["min_reader"]) == (3, 1)


def test_the_first_gate_raises_min_reader_before_the_state_is_written(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    with_track(pkg)
    seen = []
    real = pkg.history._insert

    def spy(*a, **k):
        seen.append(manifest(pkg.path)["min_reader"])
        return real(*a, **k)

    pkg.history._insert = spy
    pkg.history.commit("gate", ops.set_gate(pkg.history.state, "t", [(10, 20)]))
    assert seen == [3]  # the manifest was already stricter when the state went in
    assert manifest(pkg.path)["min_reader"] == 3
    pkg.close()


def test_an_old_reader_refuses_a_project_with_a_gate(tmp_path, monkeypatch):
    pkg = package.create(tmp_path / "A.kuulas")
    with_track(pkg)
    pkg.history.commit("gate", ops.set_gate(pkg.history.state, "t", [(10, 20)]))
    pkg.close()
    # A kuulas from before the gate: it can read format 1 and 2 only.
    monkeypatch.setattr(package, "READER", 2)
    with pytest.raises(package.PackageError) as err:
        package.open_package(tmp_path / "A.kuulas")
    assert err.value.key == "error.package.too_new"
    assert not (tmp_path / "A.kuulas" / "lock.json").exists()


def test_an_old_reader_still_opens_a_project_that_never_had_a_gate(tmp_path, monkeypatch):
    pkg = package.create(tmp_path / "A.kuulas")
    with_track(pkg)
    pkg.close()
    monkeypatch.setattr(package, "READER", 2)
    package.open_package(tmp_path / "A.kuulas").close()


def test_clearing_the_gate_does_not_lower_min_reader(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    with_track(pkg)
    pkg.history.commit("gate", ops.set_gate(pkg.history.state, "t", [(10, 20)]))
    pkg.history.commit("open", ops.set_gate(pkg.history.state, "t", []))
    pkg.close()
    assert manifest(tmp_path / "A.kuulas")["min_reader"] == 3


def test_upgrading_a_version_two_project_keeps_its_min_reader(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.close()
    folder = tmp_path / "A.kuulas"
    package.write_manifest(folder, {**manifest(folder), "version": 2, "min_reader": 1})
    package.open_package(folder).close()
    assert (manifest(folder)["version"], manifest(folder)["min_reader"]) == (3, 1)
    package.write_manifest(folder, {**manifest(folder), "version": 2, "min_reader": 3})
    package.open_package(folder).close()
    assert manifest(folder)["min_reader"] == 3


def test_the_gate_survives_save_and_load(tmp_path):
    s = Session(tmp_path / "A.kuulas")
    s.history.commit("track", ops.add_track(s.history.state, track_id="t", name="A"))
    s.history.commit("gate", ops.set_gate(s.history.state, "t", [(10, 20), (40, 50)]))
    s.close()
    again = Session(tmp_path / "A.kuulas")
    assert again.state.track("t").gate == ((10, 20), (40, 50))
    again.close()


def test_a_second_edit_of_the_project_also_raises_min_reader(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    with_track(pkg)
    pkg.history.create_edit("Short", ops.set_gate(pkg.history.state, "t", [(1, 2)]))
    assert manifest(pkg.path)["min_reader"] == 3
    pkg.close()


def test_packing_a_state_with_a_one_hour_gate_is_under_50_ms():
    # 4 mics, a closed range every 0.75 s all hour: 4,800 per mic, 19,200 in
    # all. The 300 s fixture gives 198 for four mics (2,400 an hour), so this
    # is eight times a busy hour.
    step = RATE * 3 // 4
    p = Project(rate=RATE)
    for i in range(4):
        p = ops.add_media(p, Media(id=f"m{i}", name="a.wav", channels=1,
                                   frames=3600 * RATE, sha256=f"{i:064x}"))
        p = ops.add_track(p, track_id=f"t{i}", name=f"M{i}")
        p = ops.add_clip(p, f"t{i}", f"m{i}")
        p = ops.set_gate(p, f"t{i}", [(k * step, k * step + step // 2)
                                      for k in range(4_800)])
    assert all(len(t.gate) == 4_800 for t in p.tracks)
    best = min(_time(lambda: edit_blob(p)) for _ in range(5))
    assert best < 0.050, best


def _time(fn):
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0
