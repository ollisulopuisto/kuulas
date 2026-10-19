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
    return "+".join(mods.get(part, "," if part == "Comma" else part) for part in combo.split("+"))


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


def test_export_all_tracks_and_lift_cut_are_present() -> None:
    doc = COMMITTED_DOC.read_text()
    # export.tracks is Shift+Alt+Mod+E in the keymap.
    assert "⇧+⌥+⌘+E" in doc
    assert "Shift+Alt+Ctrl+E" in doc
    # edit.lift_cut is Alt+X in the keymap.
    assert "Alt+X" in doc
    assert "⌥+X" in doc
