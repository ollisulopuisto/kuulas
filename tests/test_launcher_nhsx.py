"""Import Hindenburg from the start screen into a new project."""

import numpy as np
import pytest
import soundfile as sf

from kuulas import desktop, messages
from kuulas.session import Session


class Webview:
    class FileDialog:
        OPEN = "open"
        SAVE = "save"


class Window:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls, self.alerts = [], []

    def create_file_dialog(self, kind, **options):
        self.calls.append((kind, options))
        return next(self.answers)

    def evaluate_js(self, script):
        self.alerts.append(script)


def bridge(tmp_path, answers):
    instance = desktop.Bridge(Webview, tmp_path / "recents")
    instance._window = Window(answers)
    opened = []
    instance._opener = opened.append
    return instance, opened


def test_start_page_offers_nhsx_import_in_both_languages():
    for lang in ("en", "fi"):
        messages.set_language(lang)
        page = desktop.launcher_html([])
        assert 'id="import-nhsx"' in page
        assert messages.t("desktop.launcher.import_nhsx") in page
        assert 'wire("import-nhsx", "import", "import_nhsx_project")' in page


def test_import_creates_new_project_and_opens_after_import(tmp_path):
    source = tmp_path / "Interview.nhsx"
    sf.write(tmp_path / "speech.wav", np.zeros(4800), 48000)
    source.write_text('<Session><AudioPool><File Id="1" Name="speech.wav" '
                      'Path="speech.wav"/></AudioPool><Tracks><Track Name="Guest">'
                      '<Region Ref="1" Start="0" Length="0.1" Offset="0"/>'
                      '</Track></Tracks></Session>')
    target = tmp_path / "Interview.kuulas"
    instance, opened = bridge(tmp_path, [[str(source)], [str(target)]])
    assert instance.import_nhsx_project()
    assert opened == [str(target)]
    assert instance._window.calls[0][0] == "open"
    assert instance._window.calls[1][1]["save_filename"] == "Interview.kuulas"
    assert source.read_text().startswith('<Session>')
    session = Session(target)
    try:
        assert session.state.tracks[0].name == "Guest"
        assert len(session.state.media) == 1
    finally:
        session.close()


@pytest.mark.parametrize("answers", [[None], [["source.nhsx"], None]])
def test_cancel_does_not_create_or_open_project(tmp_path, answers):
    instance, opened = bridge(tmp_path, answers)
    assert not instance.import_nhsx_project()
    assert not opened
    assert not list(tmp_path.glob("*.kuulas"))


def test_existing_project_is_never_imported_into(tmp_path):
    target = tmp_path / "Existing.kuulas"
    target.mkdir()
    sentinel = target / "recorded.wav"
    sentinel.write_bytes(b"recording")
    instance, opened = bridge(tmp_path, [["source.nhsx"], [str(target)]])
    assert not instance.import_nhsx_project()
    assert not opened
    assert sentinel.read_bytes() == b"recording"
    assert not (target / "manifest.json").exists()
    assert instance._window.alerts


def test_bad_source_does_not_open_project(tmp_path):
    source = tmp_path / "Bad.nhsx"
    source.write_text("broken")
    instance, opened = bridge(tmp_path, [[str(source)], [str(tmp_path / "New")]])
    assert not instance.import_nhsx_project()
    assert not opened
    assert instance._window.alerts
