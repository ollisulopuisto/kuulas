from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to sys.path so scripts can be imported as modules
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_locale import (  # noqa: E402
    main,
    parity,
    referenced_keys,
    unused,
)


def test_parity_detects_mismatches_and_matches():
    en = {"a.one": "1", "common.shared": "2", "only.en": "3"}
    fi = {"a.one": "1", "common.shared": "2", "only.fi": "4"}
    only_en, only_fi = parity(en, fi)
    assert only_en == ["only.en"]
    assert only_fi == ["only.fi"]

    assert parity(en, en) == ([], [])


def test_referenced_keys_extracts_static_keys():
    text = """
    msg = t("button.play")
    other = t('error.edit.bad_kind', kind="x")
    raise KuulasError("error.common.crash")
    raise EditError('error.edit.no_clip', clip_id="1")
    ui_msg = t("ui.view.fit")
    non_key = random_function("ignore.me")
    """
    keys = referenced_keys(text)
    assert keys == {
        "button.play",
        "error.edit.bad_kind",
        "error.common.crash",
        "error.edit.no_clip",
        "ui.view.fit",
    }


def test_referenced_keys_ignores_dynamic_keys():
    text = """
    t(f"dynamic.{x}")
    t("prefix." + var)
    t(key)
    raise KuulasError(f"error.{code}")
    raise EditError("error." + name)
    """
    assert referenced_keys(text) == set()


def test_unused_keys():
    keys = {"a.b", "c.d", "e.f"}
    referenced = {"a.b", "z.x"}
    assert unused(keys, referenced) == ["c.d", "e.f"]


def test_main_cli_fails_on_parity_mismatch(tmp_path: Path, monkeypatch, capsys):
    en_file = tmp_path / "en.json"
    fi_file = tmp_path / "fi.json"
    en_file.write_text('{"a.key": "A", "b.key": "B"}', encoding="utf-8")
    fi_file.write_text('{"a.key": "A"}', encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "mod.py").write_text('t("a.key")', encoding="utf-8")
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()

    rc = main(
        [
            "--en",
            str(en_file),
            "--fi",
            str(fi_file),
            "--src",
            str(src_dir),
            "--ui",
            str(ui_dir),
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "Parity mismatch" in captured.out or "only in en" in captured.out


def test_main_cli_fails_on_missing_referenced_key(tmp_path: Path, monkeypatch, capsys):
    en_file = tmp_path / "en.json"
    fi_file = tmp_path / "fi.json"
    en_file.write_text('{"a.key": "A"}', encoding="utf-8")
    fi_file.write_text('{"a.key": "A"}', encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "mod.py").write_text('t("missing.key")', encoding="utf-8")
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()

    rc = main(
        [
            "--en",
            str(en_file),
            "--fi",
            str(fi_file),
            "--src",
            str(src_dir),
            "--ui",
            str(ui_dir),
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "missing.key" in captured.out


def test_the_recorder_package_is_not_scanned(tmp_path: Path):
    # kuulas_recorder has no catalog: its error keys are protocol keys (docs/RECORDER.md)
    # that the editor maps to error.record.*, so ProtocolError("busy", ...) is no reference.
    from scripts.check_locale import scan_sources  # noqa: PLC0415

    src = tmp_path / "src"
    (src / "kuulas_recorder").mkdir(parents=True)
    (src / "kuulas_recorder" / "supervisor.py").write_text(
        'ProtocolError("busy", "x")', encoding="utf-8")
    (src / "kuulas").mkdir()
    (src / "kuulas" / "m.py").write_text('t("a.key")', encoding="utf-8")
    assert scan_sources(src, tmp_path / "ui") == {"a.key"}


def test_the_real_tree_passes():
    assert main([]) == 0


def test_main_cli_succeeds_on_clean_locales(tmp_path: Path, capsys):
    en_file = tmp_path / "en.json"
    fi_file = tmp_path / "fi.json"
    en_file.write_text('{"a.key": "A", "unused.key": "U"}', encoding="utf-8")
    fi_file.write_text('{"a.key": "A", "unused.key": "U"}', encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "mod.py").write_text('t("a.key")', encoding="utf-8")
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()

    rc = main(
        [
            "--en",
            str(en_file),
            "--fi",
            str(fi_file),
            "--src",
            str(src_dir),
            "--ui",
            str(ui_dir),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "unused.key" in captured.out  # Warning reported
