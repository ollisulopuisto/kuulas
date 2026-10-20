"""KUULAS_LOG_LEVEL and the per-user log level setting (the bundle has no terminal)."""

import logging
import sys

import pytest

from kuulas import bundle, logsetup


@pytest.fixture(autouse=True)
def restore_root():
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    yield
    root.setLevel(level)
    root.handlers[:] = handlers


@pytest.fixture
def settings(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setenv("KUULAS_SETTINGS_FILE", str(path))
    return path


def test_default_is_info():
    assert logsetup.resolve({}, None) == "INFO"


@pytest.mark.parametrize(("value", "expected"),
                         [("DEBUG", "DEBUG"), ("debug", "DEBUG"),
                          (" Warning ", "WARNING")])
def test_environment_is_case_insensitive(value, expected):
    assert logsetup.resolve({"KUULAS_LOG_LEVEL": value}, "INFO") == expected


def test_environment_beats_the_setting():
    assert logsetup.resolve({"KUULAS_LOG_LEVEL": "DEBUG"}, "WARNING") == "DEBUG"


def test_setting_used_without_environment():
    assert logsetup.resolve({}, "WARNING") == "WARNING"


@pytest.mark.parametrize("bad", ["", "LOUD", "ERROR", "10"])
def test_unknown_values_fall_through(bad):
    assert logsetup.resolve({"KUULAS_LOG_LEVEL": bad}, "WARNING") == "WARNING"
    assert logsetup.resolve({"KUULAS_LOG_LEVEL": bad}, bad) == "INFO"


def test_source_names_where_the_level_came_from():
    assert logsetup.source({"KUULAS_LOG_LEVEL": "DEBUG"}, "INFO") == "env"
    assert logsetup.source({}, "INFO") == "setting"
    assert logsetup.source({}, None) == "default"


def test_setting_round_trip(settings):
    assert logsetup.level_setting() is None
    logsetup.save_level_setting("DEBUG")
    assert logsetup.level_setting() == "DEBUG"
    assert "DEBUG" in settings.read_text(encoding="utf-8")


def test_saving_keeps_other_settings(settings):
    settings.write_text('{"language": "fi"}', encoding="utf-8")
    logsetup.save_level_setting("WARNING")
    assert '"language": "fi"' in settings.read_text(encoding="utf-8")


def test_saving_a_bad_level_is_refused(settings):
    with pytest.raises(ValueError, match="LOUD"):
        logsetup.save_level_setting("LOUD")


def test_a_damaged_settings_file_means_no_setting(settings):
    settings.write_text("{not json", encoding="utf-8")
    assert logsetup.level_setting() is None


def test_apply_sets_the_root_level():
    logsetup.apply("DEBUG")
    assert logging.getLogger().level == logging.DEBUG
    assert logsetup.current() == "DEBUG"


def test_apply_adds_a_stream_handler_only_when_there_is_none():
    root = logging.getLogger()
    root.handlers.clear()
    logsetup.apply("INFO", console=True)
    assert len(root.handlers) == 1
    logsetup.apply("INFO", console=True)
    assert len(root.handlers) == 1


def test_the_bundle_log_honours_the_environment(tmp_path, monkeypatch, settings):
    monkeypatch.setenv("KUULAS_LOG_LEVEL", "DEBUG")
    saved = (sys.stdout, sys.stderr)
    try:
        bundle._open_log(tmp_path)
        assert logging.getLogger().level == logging.DEBUG
    finally:
        sys.stdout, sys.stderr = saved


def test_the_bundle_log_honours_the_saved_setting(tmp_path, monkeypatch, settings):
    monkeypatch.delenv("KUULAS_LOG_LEVEL", raising=False)
    logsetup.save_level_setting("WARNING")
    saved = (sys.stdout, sys.stderr)
    try:
        bundle._open_log(tmp_path)
        assert logging.getLogger().level == logging.WARNING
    finally:
        sys.stdout, sys.stderr = saved


def test_kuulas_open_applies_the_environment_level(monkeypatch, settings):
    from kuulas import cli  # noqa: PLC0415

    monkeypatch.setenv("KUULAS_LOG_LEVEL", "DEBUG")
    monkeypatch.delenv("KUULAS_PROFILE", raising=False)
    monkeypatch.setattr(cli, "open_project", lambda *_a, **_k: 0)
    assert cli.main(["open", "Some.kuulas"]) == 0
    assert logging.getLogger().level == logging.DEBUG


def test_kuulas_open_starts_a_profile_when_asked(monkeypatch, settings):
    from kuulas import cli, profiler  # noqa: PLC0415

    started = []
    monkeypatch.setenv("KUULAS_PROFILE", "12")
    monkeypatch.setattr(cli, "open_project", lambda *_a, **_k: 0)
    monkeypatch.setattr(profiler.PROFILER, "start",
                        lambda seconds, *_a: started.append(seconds))
    assert cli.main(["open", "Some.kuulas"]) == 0
    assert started == [12.0]
