import shutil
from pathlib import Path

import numpy as np
import soundfile as sf
from nhsx import read as read_nhsx

from kuulas import cli
from kuulas.session import Session

FIXTURE = (Path(__file__).parents[2] / "podcast" / "packages" / "nhsx" /
           "tests" / "data" / "h-test A.nhsx")


def test_import_nhsx_command_creates_a_project_with_the_session(tmp_path, capsys):
    nhsx_path = tmp_path / "h-test A.nhsx"
    shutil.copy(FIXTURE, nhsx_path)
    audio = tmp_path / "h-test Files"
    audio.mkdir()
    for item in read_nhsx(nhsx_path).files:
        sf.write(audio / item.name, np.zeros(48_000, dtype=np.float32), 48_000,
                 subtype="PCM_16")
    project = tmp_path / "Imported.kuulas"

    assert cli.main(["import-nhsx", str(nhsx_path), str(project)]) == 0

    assert "Imported.kuulas" in capsys.readouterr().out
    session = Session(project)
    try:
        assert len(session.state.tracks) == 6
    finally:
        session.close()


def test_import_nhsx_command_reports_a_bad_file(tmp_path, capsys):
    bad = tmp_path / "bad.nhsx"
    bad.write_text("not xml")
    assert cli.main(["import-nhsx", str(bad), str(tmp_path / "X.kuulas")]) == 1
    assert capsys.readouterr().err
