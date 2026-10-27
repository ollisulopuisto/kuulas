"""Security hardening for docs/design/prototype/index.html (CodeQL findings).

CodeQL js/unvalidated-dynamic-method-call fires on ``PAGES[S.screen]``: ``S.screen``
comes from the URL, so an attacker-controlled key could reach inherited
properties such as ``PAGES.constructor``. The lookup must go through a ``Map``
so only the five registered renderers can ever be returned, and the call must
still be guarded by ``typeof === "function"``.
"""

from pathlib import Path

PROTOTYPE = (
    Path(__file__).resolve().parent.parent
    / "docs" / "design" / "prototype" / "index.html"
)


def test_dynamic_method_call_uses_map_lookup() -> None:
    """S.screen may only select one of the renderers registered in the Map."""
    source = PROTOTYPE.read_text(encoding="utf8")
    assert "const PAGES = new Map([" in source, (
        "PAGES must be a Map so inherited properties are never reached"
    )
    assert "PAGES[S.screen]" not in source, (
        "dynamic property access with a user-controlled key remains"
    )
    idx = source.index("const page = PAGES.get(S.screen);")
    after = source[idx:]
    # The call itself must still check that the value is a function.
    assert 'typeof page === "function"' in after.split('if (!$("topbar"))')[0], (
        "page() call is not guarded by a function check"
    )


def test_theme_is_html_escaped() -> None:
    """S.theme must be escapeHtml-escaped before interpolation into HTML."""
    source = PROTOTYPE.read_text(encoding="utf8")
    assert "escapeHtml(S.theme)" in source, "S.theme is interpolated unescaped"


def test_density_is_html_escaped() -> None:
    """S.density is also user-controlled (the URL) and interpolated into HTML."""
    source = PROTOTYPE.read_text(encoding="utf8")
    assert "escapeHtml(S.density)" in source, "S.density is interpolated unescaped"


def test_motion_is_html_escaped() -> None:
    """S.motion is also user-controlled (the URL) and interpolated into HTML."""
    source = PROTOTYPE.read_text(encoding="utf8")
    assert "escapeHtml(S.motion)" in source, "S.motion is interpolated unescaped"
