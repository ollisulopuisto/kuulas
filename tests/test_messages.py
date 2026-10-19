"""Messages: the catalogs, the never-raising ``t``, and the speechmix translator.

Several of these read the source tree on purpose: a message that is raised
without a catalog key is a Finnish user seeing English, and only a scan of
the code finds it.
"""

import ast
import json
import os
import string
import subprocess
import sys
from pathlib import Path

import pytest
from speechmix import messages as speechmix_messages

from kuulas import media, messages, ops, transcribe

SRC = Path(__file__).resolve().parents[1] / "src" / "kuulas"


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English, whatever the machine's locale says."""
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture(autouse=True)
def no_apple_languages(monkeypatch):
    """This Mac's real language list must not decide the tests' language."""
    monkeypatch.setattr(messages, "_apple_languages", list)


def _placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def _placeholder_sets(entry) -> dict[str, set[str]]:
    """Placeholders per plural category, or ``{"": ...}`` for a plain value."""
    if isinstance(entry, dict):
        return {cat: _placeholders(text) for cat, text in entry.items()}
    return {"": _placeholders(entry)}


def _catalog(lang: str) -> dict:
    return messages._CATALOGS[lang]


def _python_sources():
    for path in sorted(SRC.glob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_catalogs_have_identical_keys_and_placeholders():
    en, fi = _catalog("en"), _catalog("fi")
    assert set(en) == set(fi)
    for key in en:
        en_sets, fi_sets = _placeholder_sets(en[key]), _placeholder_sets(fi[key])
        assert set(en_sets) == set(fi_sets), key
        for category in en_sets:
            assert en_sets[category] == fi_sets[category], (key, category)


def test_plural_entries_pick_a_category_by_count(monkeypatch):
    monkeypatch.setitem(_catalog("en"), "test.clips",
                        {"one": "{count} clip", "other": "{count} clips"})
    monkeypatch.setitem(_catalog("fi"), "test.clips",
                        {"one": "{count} klippi", "other": "{count} klippiä"})
    assert messages.t("test.clips", count=1) == "1 clip"
    assert messages.t("test.clips", count=3) == "3 clips"
    messages.set_language("fi")
    assert messages.t("test.clips", count=3) == "3 klippiä"


def test_unknown_key_falls_back_to_english_then_key(monkeypatch):
    messages.set_language("fi")
    monkeypatch.delitem(_catalog("fi"), "error.edit.no_clip")
    # Not in Finnish: the English text, not the key.
    assert messages.t("error.edit.no_clip", clip_id="c1") == "There is no clip c1."
    # In neither catalog: the key itself, with the values so it still says something.
    assert messages.t("no.such.key") == "no.such.key"
    assert messages.t("no.such.key", a=1) == "no.such.key (a=1)"


def test_missing_value_never_raises():
    assert messages.t("error.edit.no_clip") == "There is no clip {clip_id}."
    text = messages.t("audio.plugin_shifted", name="take 1")
    assert "take 1" in text
    assert "{samples}" in text
    # A value the format spec cannot take must not raise either.
    assert isinstance(
        messages.t("audio.plugin_shifted", samples=1, ms="abc", name="x"), str)


def test_default_language_follows_the_os_locale(monkeypatch):
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "fi_FI.UTF-8")
    assert messages.default_language() == "fi"
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert messages.default_language() == "en"
    monkeypatch.setenv("LANG", "sv_SE.UTF-8")
    assert messages.default_language() == "en"
    # LC_ALL outranks LANG, as in POSIX.
    monkeypatch.setenv("LC_ALL", "fi_FI.UTF-8")
    assert messages.default_language() == "fi"


def test_error_body_has_key_params_and_text():
    body = messages.error_body("error.edit.no_clip", clip_id="c1")
    assert body == {"error": {"key": "error.edit.no_clip",
                              "params": {"clip_id": "c1"},
                              "text": "There is no clip c1."}}
    messages.set_language("fi")
    assert messages.error_body("error.edit.no_clip", clip_id="c1")["error"]["text"] == (
        "Leikettä c1 ei ole.")


def test_error_body_params_are_json_safe(tmp_path):
    body = messages.error_body("error.edit.no_clip", clip_id=tmp_path)
    assert body["error"]["params"] == {"clip_id": str(tmp_path)}


def test_exception_text_is_translated_at_read_time():
    err = ops.EditError("error.edit.no_clip", clip_id="c1")
    assert isinstance(err, ValueError)
    assert err.key == "error.edit.no_clip"
    assert err.params == {"clip_id": "c1"}
    assert str(err) == "There is no clip c1."
    messages.set_language("fi")
    assert str(err) == "Leikettä c1 ei ole."


def test_media_and_transcribe_errors_keep_their_base_classes():
    assert issubclass(media.MediaError, RuntimeError)
    assert issubclass(transcribe.TranscribeError, RuntimeError)
    assert issubclass(media.MediaError, messages.KuulasError)
    assert issubclass(transcribe.TranscribeError, messages.KuulasError)


def test_speechmix_messages_are_translated():
    for key, english_text in speechmix_messages.FALLBACK.items():
        # The English copy in our catalog is the same text, so a change in
        # speechmix's English makes the Finnish stale and this test says so.
        assert _catalog("en")[key] == english_text, key
        finnish = _catalog("fi")[key]
        assert finnish, key
        assert finnish != english_text, key


def test_speechmix_messages_come_out_in_finnish():
    messages.set_language("fi")
    for key, english_text in speechmix_messages.FALLBACK.items():
        values = dict.fromkeys(_placeholders(english_text), 1.0)
        translated = speechmix_messages.t(key, **values)
        assert translated != english_text.format(**values), key
        assert translated == messages.t(key, **values), key


def test_speechmix_key_unknown_to_kuulas_falls_back_to_speechmix_english(monkeypatch):
    monkeypatch.setitem(speechmix_messages.FALLBACK, "test.new_speechmix_key",
                        "A new message: {name}")
    messages.set_language("fi")
    assert speechmix_messages.t("test.new_speechmix_key", name="x") == (
        "A new message: x")


def test_every_used_key_exists():
    # Keys are used two ways: t("key") calls, and the first argument of an
    # exception built with a key (raise EditError("error.edit.no_clip", ...)).
    keys = set(_catalog("en"))
    used: set[str] = set()
    for _, tree in _python_sources():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            is_key_call = name == "t" or name.endswith("Error")
            first = node.args[0] if node.args else None
            is_text = isinstance(first, ast.Constant) and isinstance(first.value, str)
            if is_key_call and is_text:
                used.add(first.value)
    assert used, "the scan found no keys; it is looking in the wrong place"
    assert used <= keys, sorted(used - keys)


def _has_string_text(node: ast.AST) -> bool:
    """Does this expression build text: an f-string, a literal, or concatenation?"""
    for child in ast.walk(node):
        if isinstance(child, ast.JoinedStr):
            return True
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            return True
    return False


def test_no_literal_user_messages_in_python():
    keys = set(_catalog("en"))
    offenders = []
    for path, tree in _python_sources():
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)):
                continue
            for arg in node.exc.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    # A literal is allowed only as a catalog key.
                    if arg.value not in keys:
                        offenders.append(f"{path.name}:{node.lineno} {arg.value!r}")
                elif _has_string_text(arg):
                    offenders.append(f"{path.name}:{node.lineno} text in exception")
    assert not offenders, offenders


def test_locale_files_ship_with_the_package(tmp_path):
    # From another directory, so the import cannot find the source tree by luck.
    code = ("from kuulas import messages as m; m.set_language('en'); "
            "print(m.t('error.edit.no_clip', clip_id='c'))")
    # Pin the language in the code: a Finnish Mac says so through ``defaults``
    # whatever the environment holds, and the test is about the files.
    env = {k: v for k, v in os.environ.items() if k not in ("LC_ALL", "LC_MESSAGES")}
    env["LANG"] = "en_US.UTF-8"
    out = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-c", code], cwd=tmp_path, env=env,
        capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "There is no clip c."


@pytest.mark.parametrize("lang", ["en", "fi"])
def test_catalog_files_are_valid_json(lang):
    path = SRC / "locales" / f"{lang}.json"
    assert json.loads(path.read_text(encoding="utf-8")) == messages._CATALOGS[lang]


APPLE_FINNISH = '(\n    "fi-FI",\n    "en-FI"\n)\n'


@pytest.fixture
def mac(monkeypatch):
    """A Mac whose Terminal says LANG=en_US while the system language is whatever
    ``defaults`` is made to print."""
    monkeypatch.undo()  # drop the autouse stub: these tests drive the real parser
    monkeypatch.setattr(sys, "platform", "darwin")
    for var in ("LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    return monkeypatch


def _defaults(monkeypatch, stdout="", returncode=0, raises=None):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        if raises:
            raise raises
        return subprocess.CompletedProcess(argv, returncode, stdout, "")

    monkeypatch.setattr(messages.subprocess, "run", fake_run)
    return calls


def test_macos_system_language_list_outranks_lang(mac):
    calls = _defaults(mac, APPLE_FINNISH)
    assert messages.default_language() == "fi"
    argv, kwargs = calls[0]
    assert argv == ["defaults", "read", "-g", "AppleLanguages"]
    assert kwargs["timeout"] > 0  # a hung tool must not hang start-up


def test_macos_takes_the_first_language_we_ship(mac):
    _defaults(mac, '(\n    "sv-FI",\n    "fi-FI"\n)\n')
    assert messages.default_language() == "fi"
    _defaults(mac, '(\n    "sv-FI",\n    "de-DE"\n)\n')
    assert messages.default_language() == "en"


def test_macos_falls_back_to_lang_when_defaults_fails(mac):
    mac.setenv("LANG", "fi_FI.UTF-8")
    _defaults(mac, "", returncode=1)
    assert messages.default_language() == "fi"
    _defaults(mac, raises=FileNotFoundError("defaults"))
    assert messages.default_language() == "fi"
    _defaults(mac, raises=subprocess.TimeoutExpired("defaults", 2))
    assert messages.default_language() == "fi"


def test_explicit_lc_all_still_outranks_the_macos_list(mac):
    _defaults(mac, APPLE_FINNISH)
    mac.setenv("LC_ALL", "en_GB.UTF-8")
    assert messages.default_language() == "en"


def test_other_systems_never_run_defaults(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("LANG", "fi_FI.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    calls = _defaults(monkeypatch, APPLE_FINNISH)
    assert messages.default_language() == "fi"
    assert not calls


def test_catalog_for_the_ui_is_the_whole_catalog():
    assert messages.catalog("fi") == messages._CATALOGS["fi"]
    assert messages.catalog("xx") is None
