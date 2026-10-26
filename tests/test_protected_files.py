"""Protected files: never delete recordings or linked media by mistake."""

import os

import pytest

from kuulas.protected_files import check_delete, is_protected


def mk(p: str) -> str:
    """Make an absolute path that is valid on both POSIX and Windows."""
    if os.name == "nt" and p.startswith("/"):
        return "C:" + p
    return p


ROOT = mk("/Users/dst/project")
RECORDINGS = mk("/Users/dst/project/recordings")
MEDIA = (mk("/Users/dst/media/song.wav"), mk("/Users/dst/media/jingle.wav"))


def test_is_protected_inside_recordings_at_any_depth():
    assert is_protected(f"{RECORDINGS}/take.wav", ROOT) is True
    assert is_protected(f"{RECORDINGS}/sessions/s1/take 3.wav", ROOT) is True


def test_is_protected_recordings_dir_itself():
    assert is_protected(RECORDINGS, ROOT) is True


def test_is_protected_outside_recordings():
    assert is_protected(mk("/Users/dst/project/other/take.wav"), ROOT) is False
    assert is_protected(mk("/Users/dst/project/recordingsx/take.wav"), ROOT) is False
    assert is_protected(mk("/Users/dst/other/recordings/take.wav"), ROOT) is False


def test_is_protected_dotdot_tricks():
    assert is_protected(f"{RECORDINGS}/../x/take.wav", ROOT) is False
    assert is_protected(mk("/Users/dst/project/x/../recordings/take.wav"), ROOT) is True
    assert is_protected(f"{RECORDINGS}/a/../../recordings/b.wav", ROOT) is True


def test_is_protected_media_paths():
    assert is_protected(mk("/Users/dst/media/song.wav"), ROOT, media_paths=MEDIA) is True
    assert is_protected(mk("/Users/dst/media/jingle.wav"), ROOT,
                        media_paths=MEDIA) is True
    assert is_protected(mk("/Users/dst/media/other.wav"), ROOT,
                        media_paths=MEDIA) is False
    assert is_protected(f"{RECORDINGS}/take.wav", ROOT, media_paths=MEDIA) is True


def test_is_protected_case_sensitive():
    assert is_protected(mk("/Users/dst/Project/recordings/take.wav"), ROOT) is False
    assert is_protected(RECORDINGS.upper(), ROOT) is False


def test_is_protected_relative_paths_raise():
    with pytest.raises(ValueError, match="project_root"):
        is_protected(f"{RECORDINGS}/take.wav", "relative/root")
    with pytest.raises(ValueError, match="path"):
        is_protected("recordings/take.wav", ROOT)
    with pytest.raises(ValueError, match="media_paths"):
        is_protected(f"{RECORDINGS}/take.wav", ROOT, media_paths=("relative/media.wav",))


def test_check_delete_not_protected_is_ok():
    assert check_delete(mk("/Users/dst/project/other/take.wav"), ROOT) == "ok"


def test_check_delete_protected_refused_unless_confirmed():
    assert check_delete(f"{RECORDINGS}/take.wav", ROOT) == "refused"
    assert check_delete(f"{RECORDINGS}/take.wav", ROOT, confirmed=False) == "refused"
    assert check_delete(f"{RECORDINGS}/take.wav", ROOT, confirmed=True) == "ok"


def test_check_delete_media_path():
    target = mk("/Users/dst/media/song.wav")
    assert check_delete(target, ROOT, media_paths=MEDIA) == "refused"
    assert (
        check_delete(target, ROOT, media_paths=MEDIA, confirmed=True)
        == "ok"
    )
