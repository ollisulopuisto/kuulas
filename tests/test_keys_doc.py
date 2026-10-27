"""Tests for scripts/make_keys_doc.mjs."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "make_keys_doc.mjs"
COMMITTED_DOC = ROOT / "docs" / "KEYS.md"


def _run_node(code: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed node argv, no shell
        ["node", "-e", code],  # noqa: S607 - node is on PATH
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _load_keymap() -> dict:
    code = (
        "import('./ui/keymap-default.js').then(m => "
        "console.log(JSON.stringify({"
        "DEFAULT_KEYMAP: m.DEFAULT_KEYMAP, CONTEXTS: m.CONTEXTS"
        "})))"
    )
    return json.loads(_run_node(code))


def _format_combo(combo: str, mods: dict[str, str]) -> str:
    names = {**mods, "Comma": ","}
    return "+".join(names.get(part, part) for part in combo.split("+"))


def _format_entry_keys(keys: str | list[str] | None, mods: dict[str, str]) -> str:
    if keys is None:
        return ""
    if isinstance(keys, list):
        return " or ".join(_format_combo(k, mods) for k in keys)
    return _format_combo(keys, mods)


MAC_MODS = {"Mod": "⌘", "Alt": "⌥", "Shift": "⇧", "Ctrl": "⌃"}
OTHER_MODS = {"Mod": "Ctrl", "Alt": "Alt", "Shift": "Shift", "Ctrl": "Ctrl"}


def _all_keymap_keys(keymap_data: dict) -> set[str]:
    combos: set[str] = set()
    for entry in keymap_data["DEFAULT_KEYMAP"]:
        keys = entry.get("keys")
        if not keys:
            continue
        mac = keys.get("mac")
        other = keys.get("other")
        if mac is not None:
            combos.add(_format_entry_keys(mac, MAC_MODS))
        if other is not None:
            combos.add(_format_entry_keys(other, OTHER_MODS))
    return combos


def _parse_doc_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        parts = [part.strip() for part in line.split("|")]
        parts = [part for part in parts if part]
        if len(parts) < 4 or parts[0] in ("Key (Mac)", "---"):
            continue
        mac, other = parts[0], parts[1]
        if mac:
            keys.add(mac)
        if other:
            keys.add(other)
    return keys


def test_keys_doc_is_up_to_date(tmp_path: Path) -> None:
    out = tmp_path / "KEYS.md"
    subprocess.run(  # noqa: S603 - fixed node argv, no shell
        ["node", str(SCRIPT), str(out)],  # noqa: S607 - node is on PATH
        cwd=ROOT,
        check=True,
    )
    assert out.read_text() == COMMITTED_DOC.read_text()


def test_every_doc_key_is_in_keymap() -> None:
    doc = COMMITTED_DOC.read_text()
    keymap_data = _load_keymap()
    doc_keys = _parse_doc_keys(doc)
    keymap_keys = _all_keymap_keys(keymap_data)
    extra = doc_keys - keymap_keys
    assert not extra, f"doc keys not in DEFAULT_KEYMAP: {extra}"


def test_export_keys_and_lift_cut_are_present() -> None:
    doc = COMMITTED_DOC.read_text()
    # Owner 2026-10-21: Shift+Mod+E is the automixer export, Alt+Mod+E the mix options;
    # the all-tracks exports have no key.
    assert "⇧+⌘+E" in doc
    assert "Shift+Ctrl+E" in doc
    assert "⌥+⌘+E" in doc
    assert "⇧+⌥+⌘+E" not in doc
    # edit.lift_cut is Alt+X in the keymap.
    assert "Alt+X" in doc
    assert "⌥+X" in doc


def test_escape_cell_escapes_table_breakers() -> None:
    """escapeCell must keep markdown table cells intact: ``|`` splits columns
    and line breaks split rows, so both must be neutralised."""
    code = (
        "import('./scripts/make_keys_doc.mjs').then(m => {"
        "console.log(JSON.stringify({"
        "pipe: m.escapeCell('a|b'),"
        "backslash: m.escapeCell('a\\\\b'),"
        "newline: m.escapeCell('a\\nb'),"
        "cr: m.escapeCell('a\\rb'),"
        "crlf: m.escapeCell('a\\r\\nb')"
        "}));"
        "})"
    )
    result = json.loads(_run_node(code))
    assert "\\|" in result["pipe"], f"pipe not escaped: {result['pipe']!r}"
    pipe_without_escapes = result["pipe"].replace("\\|", "")
    assert "|" not in pipe_without_escapes, f"raw pipe remains: {result['pipe']!r}"
    # A backslash in the input must be escaped so it cannot turn the next
    # character into an escape sequence (e.g. ``\\|`` would otherwise render
    # as a literal pipe). The result must not contain a lone backslash before
    # the pipe.
    assert result["backslash"] == "a\\\\b", (
        f"backslash not escaped: {result['backslash']!r}"
    )
    for key in ("newline", "cr", "crlf"):
        assert "\n" not in result[key], f"newline not escaped: {result[key]!r}"
        assert "\r" not in result[key], f"carriage return not escaped: {result[key]!r}"


def test_generated_hints_render_command_tokens(tmp_path: Path) -> None:
    out = tmp_path / "KEYS.md"
    subprocess.run(  # noqa: S603 - fixed node argv, no shell
        ["node", str(SCRIPT), str(out)],  # noqa: S607 - node is on PATH
        cwd=ROOT,
        check=True,
    )
    doc = out.read_text()
    assert "{key:" not in doc
    assert "Options: Export mix (options)…" in doc


def test_escape_cell_sanitizes_markdown_table_breakers() -> None:
    """escapeCell must escape characters that break markdown table structure:
    ``|`` (column separator) and newlines/carriage returns (row breaks)."""
    code = (
        "import('./scripts/make_keys_doc.mjs').then(m => {"
        "const cases = ['a|b', 'a\\nb', 'a\\rb', 'plain', 'x|y\\nz', 'a\\r\\nb'];"
        "console.log(JSON.stringify(cases.map(c => m.escapeCell(c))));"
        "});"
    )
    out = _run_node(code)
    results = json.loads(out)
    assert results[0] == "a\\|b", results
    assert results[1] == "a b", results  # LF becomes space
    assert results[2] == "a b", results  # CR becomes space
    assert results[3] == "plain", results
    assert results[4] == "x\\|y z", results  # both | and LF escaped
    assert results[5] == "a b", results  # CRLF becomes single space
