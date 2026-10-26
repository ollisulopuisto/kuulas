"""Protected files: never delete recordings or linked media by mistake."""

from pathlib import Path

import pytest

from kuulas.protected_files import check_delete, is_protected

ROOT = Path.cwd() / "kuulas-test-project"
RECORDINGS = ROOT / "recordings"
MEDIA = (ROOT.parent / "media" / "song.wav", ROOT.parent / "media" / "jingle.wav")
MEDIA_PATHS = tuple(map(str, MEDIA))


def path(*parts: str) -> str:
    return str(Path(*parts))


def test_is_protected_inside_recordings_at_any_depth():
    assert is_protected(path(str(RECORDINGS), "take.wav"), str(ROOT)) is True
    assert is_protected(path(str(RECORDINGS), "sessions", "s1", "take 3.wav"),
                        str(ROOT)) is True


def test_is_protected_recordings_dir_itself():
    assert is_protected(str(RECORDINGS), str(ROOT)) is True


def test_is_protected_outside_recordings():
    assert is_protected(path(str(ROOT), "other", "take.wav"), str(ROOT)) is False
    assert is_protected(path(str(ROOT), "recordingsx", "take.wav"), str(ROOT)) is False
    assert is_protected(path(str(ROOT.parent / "other"), "recordings", "take.wav"),
                        str(ROOT)) is False


def test_is_protected_dotdot_tricks():
    assert is_protected(path(str(RECORDINGS), "..", "x", "take.wav"), str(ROOT)) is False
    assert is_protected(path(str(ROOT), "x", "..", "recordings", "take.wav"),
                        str(ROOT)) is True
    assert is_protected(path(str(RECORDINGS), "a", "..", "..", "recordings", "b.wav"),
                        str(ROOT)) is True


def test_is_protected_media_paths():
    assert is_protected(str(MEDIA[0]), str(ROOT), media_paths=MEDIA_PATHS) is True
    assert is_protected(str(MEDIA[1]), str(ROOT), media_paths=MEDIA_PATHS) is True
    assert is_protected(str(MEDIA[0].with_name("other.wav")), str(ROOT),
                        media_paths=MEDIA_PATHS) is False
    assert is_protected(path(str(RECORDINGS), "take.wav"), str(ROOT),
                        media_paths=MEDIA_PATHS) is True


def test_is_protected_case_sensitive():
    other_case_root = ROOT.with_name("Kuulas-Test-Project")
    assert is_protected(path(str(other_case_root), "recordings", "take.wav"),
                        str(ROOT)) is False
    assert is_protected(str(RECORDINGS).upper(), str(ROOT)) is False


def test_is_protected_relative_paths_raise():
    with pytest.raises(ValueError, match="project_root"):
        is_protected(path(str(RECORDINGS), "take.wav"), "relative/root")
    with pytest.raises(ValueError, match="path"):
        is_protected(path("recordings", "take.wav"), str(ROOT))
    with pytest.raises(ValueError, match="media_paths"):
        is_protected(path(str(RECORDINGS), "take.wav"), str(ROOT),
                     media_paths=("relative/media.wav",))


def test_check_delete_not_protected_is_ok():
    assert check_delete(path(str(ROOT), "other", "take.wav"), str(ROOT)) == "ok"


def test_check_delete_protected_refused_unless_confirmed():
    target = path(str(RECORDINGS), "take.wav")
    assert check_delete(target, str(ROOT)) == "refused"
    assert check_delete(target, str(ROOT), confirmed=False) == "refused"
    assert check_delete(target, str(ROOT), confirmed=True) == "ok"


def test_check_delete_media_path():
    assert check_delete(str(MEDIA[0]), str(ROOT), media_paths=MEDIA_PATHS) == "refused"
    assert (
        check_delete(str(MEDIA[0]), str(ROOT), media_paths=MEDIA_PATHS, confirmed=True)
        == "ok"
    )
