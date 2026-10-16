import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

from kuulas.session import Session

RATE = 48_000


def write_linked(path: Path, seed: int) -> Path:
    rng = np.random.default_rng(seed)
    sf.write(path, rng.uniform(-0.5, 0.5, RATE).astype(np.float32), RATE,
             subtype="PCM_16")
    return path


def make_project(root: Path, names=("one.wav", "two.wav")) -> tuple[Path, list[str]]:
    root.mkdir(parents=True)
    audio = root / "Audio"
    audio.mkdir()
    paths = [write_linked(audio / name, i + 1) for i, name in enumerate(names)]
    project = root / "Project" / "Interview.kuulas"
    project.parent.mkdir()
    session = Session(project)
    try:
        session.import_media([str(path) for path in paths])
        ids = [session.store.find(path) for path in paths]
    finally:
        session.close()
    return project, ids


def test_project_copy_resolves_media_relative_to_the_package(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    original_root = tmp_path / "machine-a"
    project, ids = make_project(original_root)
    copied_root = tmp_path / "machine-b"
    shutil.copytree(original_root, copied_root)
    shutil.rmtree(original_root / "Audio")

    session = Session(copied_root / "Project" / project.name)
    try:
        session.store.wait_for_resolution(timeout=5)
        assert session.store.missing() == []
        assert all(np.any(session.store.read(media_id, 0, 100)) for media_id in ids)
        for media_id in ids:
            meta = session.store.meta(media_id)
            assert meta["linked_package_rel"] == f"../../Audio/{meta['name']}"
    finally:
        session.close()


def test_media_folders_search_by_hash_and_reject_same_named_wrong_content(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    original_root = tmp_path / "machine-a"
    project, ids = make_project(original_root, names=("one.wav",))
    moved = tmp_path / "machine-b" / "Audio"
    moved.mkdir(parents=True)
    write_linked(moved / "one.wav", 21)  # Same name and size, different bytes.
    shutil.rmtree(original_root / "Audio")

    session = Session(tmp_path / "machine-a" / "Project" / project.name)
    try:
        session.store.set_media_folders([moved])
        assert session.store.relink() == {}
        assert session.store.missing() == ids

        write_linked(moved / "one.wav", 1)
        found = session.store.relink()
        assert found == {ids[0]: str((moved / "one.wav").resolve())}
        assert session.store.missing() == []
    finally:
        session.close()


def test_relink_one_learns_a_rewrite_for_the_other_missing_media(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    original_root = tmp_path / "Volumes" / "Raid" / "Kapina"
    project, ids = make_project(original_root)
    relocated = tmp_path / "Users" / "listener" / "Dropbox" / "Kapina" / "Audio"
    relocated.mkdir(parents=True)
    for index, name in enumerate(("one.wav", "two.wav"), start=1):
        write_linked(relocated / name, index)
    shutil.rmtree(original_root / "Audio")

    session = Session(project)
    try:
        found = session.store.relink_one(ids[0], relocated / "one.wav")
        assert found[ids[0]] == str((relocated / "one.wav").resolve())
        assert found[ids[1]] == str((relocated / "two.wav").resolve())
        assert session.store.missing() == []
        assert session.store.path_rewrites()
    finally:
        session.close()


def test_rewrite_and_media_folders_are_remembered_per_user(tmp_path, monkeypatch):
    config = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    original_root = tmp_path / "machine-a"
    project, ids = make_project(original_root, names=("one.wav",))
    relocated = tmp_path / "machine-b" / "Media"
    relocated.mkdir(parents=True)
    write_linked(relocated / "one.wav", 1)
    shutil.rmtree(original_root / "Audio")

    session = Session(project)
    try:
        session.store.set_media_folders([relocated])
        session.store.relink_one(ids[0], relocated / "one.wav")
    finally:
        session.close()

    assert (config / "kuulas" / "media.json").is_file()
