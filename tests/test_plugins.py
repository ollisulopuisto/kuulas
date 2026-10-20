"""Installed audio plug-ins: the scanner (a fake tree, nothing is loaded), the fuzzy
matcher (the same rule as ui/plugin-match.js) and names resolved to paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from kuulas import automix, plugins


def make_tree(root: Path) -> Path:
    for rel in ("VST3/Accentize dxRevive.vst3/Contents/x", "VST3/Other.vst3/Contents/x",
                "Components/Accentize dxRevive.component/Contents/x",
                "Components/Only AU.component/Contents/x",
                "VST/Accentize dxRevive.vst/Contents/x", "VST/readme.txt"):
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("not a plug-in; must never be read")
    return root


def test_scan_lists_bundles_with_format_and_absolute_path(tmp_path):
    root = make_tree(tmp_path / "Plug-Ins")
    found = plugins.scan([root / "VST3", root / "Components", root / "VST"])
    got = {(p["name"], p["format"]) for p in found}
    assert got == {("Accentize dxRevive", "VST3"), ("Other", "VST3"),
                   ("Accentize dxRevive", "AU"), ("Only AU", "AU"),
                   ("Accentize dxRevive", "VST2")}
    for p in found:
        assert Path(p["path"]).is_absolute()
        assert Path(p["path"]).exists()


def test_scan_ignores_missing_folders_and_loose_files(tmp_path):
    assert plugins.scan([tmp_path / "nope"]) == []


def test_scan_does_not_follow_a_symlink_out_of_the_folder(tmp_path):
    root = make_tree(tmp_path / "Plug-Ins")
    outside = tmp_path / "elsewhere" / "Evil.vst3"
    outside.mkdir(parents=True)
    (root / "VST3" / "Evil.vst3").symlink_to(outside, target_is_directory=True)
    (root / "VST3" / "dir").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    names = {p["name"] for p in plugins.scan([root / "VST3"])}
    assert "Evil" not in names


def test_scan_does_not_go_deep(tmp_path):
    deep = tmp_path / "VST3" / "a" / "b" / "c" / "Deep.vst3"
    deep.mkdir(parents=True)
    assert plugins.scan([tmp_path / "VST3"]) == []


def test_roots_per_platform(tmp_path):
    mac = plugins.roots("darwin", tmp_path)
    assert Path("/Library/Audio/Plug-Ins/VST3") in mac
    assert tmp_path / "Library/Audio/Plug-Ins/Components" in mac
    assert any("vst3" in str(r).lower() for r in plugins.roots("linux", tmp_path))
    assert plugins.roots("plan9", tmp_path) == []


def test_list_is_cached_until_refresh(monkeypatch):
    calls = []
    monkeypatch.setattr(plugins, "scan", lambda *a, **k: calls.append(1) or [])
    plugins.list_plugins(refresh=True)
    plugins.list_plugins()
    assert len(calls) == 1
    plugins.list_plugins(refresh=True)
    assert len(calls) == 2


def entries(*specs):
    return [{"name": n, "format": f, "path": f"/p/{f}/{n}"} for n, f in specs]


DX = entries(("Accentize dxRevive", "VST3"), ("Accentize dxRevive", "AU"),
             ("Accentize dxRevive", "VST2"), ("Waves NS1", "VST3"),
             ("FabFilter Pro-Q 3", "AU"), ("Reverb", "VST3"))


@pytest.mark.parametrize("query", ["dxrev", "accentize dx", "dxrevi", "DXREVIVE",
                                   "accentize-dxrevive", "dx revive", "dxrevie",
                                   "acc dxr", "dxrvive"])
def test_dxrevive_is_found(query):
    top = plugins.match(query, DX)[0]
    assert top["name"] == "Accentize dxRevive"
    assert top["format"] == "VST3"


def test_rank_exact_prefix_word_prefix_subsequence():
    items = entries(("xreverb", "VST3"), ("Reverb", "VST3"), ("Big Reverb", "VST3"),
                    ("Reverb Plus", "VST3"))
    got = plugins.match("reverb", items)
    tiers = {m["name"]: m["tier"] for m in got}
    assert tiers == {"Reverb": "exact", "Reverb Plus": "prefix", "Big Reverb": "word",
                     "xreverb": "subsequence"}
    assert [m["name"] for m in got] == ["Reverb", "Reverb Plus", "Big Reverb", "xreverb"]


def test_one_entry_per_name_best_format_wins():
    got = plugins.match("dxrevive", DX)
    assert [m["format"] for m in got if m["name"].startswith("Accentize")] == ["VST3"]
    foo = entries(("Foo", "VST2"), ("Foo", "AU"))
    assert plugins.match("foo", foo)[0]["format"] == "AU"


def test_typo_needs_five_characters():
    assert plugins.match("wvae", entries(("Wave", "VST3"))) == []  # name under 5 letters
    assert plugins.match("wv", entries(("Waves", "VST3")))[0]["tier"] == "subsequence"
    assert plugins.match("wvaes", entries(("Waves", "VST3")))[0]["tier"] == "typo"
    assert plugins.match("abx", entries(("abc", "VST3"))) == []


def test_limit_and_highlight_indices():
    many = entries(*[(f"Comp {i}", "VST3") for i in range(30)])
    assert len(plugins.match("comp", many, limit=5)) == 5
    top = plugins.match("dxrev", DX)[0]
    assert "".join(top["name"][i] for i in top["indices"]).lower() == "dxrev"


def test_nothing_matches():
    assert plugins.match("zzzzqqq", DX) == []
    assert plugins.match("", DX) == []


# -- option normalisation -------------------------------------------------------------


@pytest.fixture
def installed(monkeypatch, tmp_path):
    bundle = tmp_path / "VST3" / "Accentize dxRevive.vst3"
    bundle.mkdir(parents=True)
    other = tmp_path / "VST3" / "Other.vst3"
    other.mkdir()
    items = [{"name": "Accentize dxRevive", "format": "VST3", "path": str(bundle)},
             {"name": "Other", "format": "VST3", "path": str(other)}]
    monkeypatch.setattr(plugins, "list_plugins", lambda refresh=False: items)
    return items


def test_names_become_paths(installed):
    got = automix.normalize_options({"speech_plugins": ["dxrev"],
                                     "music_plugins": ["Other"]})
    assert got == {"speech_plugins": [installed[0]["path"]],
                   "music_plugins": [installed[1]["path"]]}


def test_an_existing_path_is_kept_and_a_missing_one_refused(installed, tmp_path):
    real = tmp_path / "My Own.vst3"
    real.mkdir()
    assert automix.normalize_options({"speech_plugins": [str(real)]}) == {
        "speech_plugins": [str(real)]}
    with pytest.raises(automix.AutomixError):
        automix.normalize_options({"speech_plugins": [str(tmp_path / "gone.vst3")]})


def test_an_unknown_name_is_refused_when_plugins_are_installed(installed):
    with pytest.raises(automix.AutomixError):
        automix.normalize_options({"speech_plugins": ["zzzqqq"]})


def test_without_a_scan_a_name_passes_through(monkeypatch):
    monkeypatch.setattr(plugins, "list_plugins", lambda refresh=False: [])
    assert automix.normalize_options({"speech_plugins": ["dxRevive"]}) == {
        "speech_plugins": ["dxRevive"]}


def test_switch_shaped_and_control_characters_stay_refused(installed):
    for bad in ("--x", "a\nb"):
        with pytest.raises(automix.AutomixError):
            automix.normalize_options({"speech_plugins": [bad]})
