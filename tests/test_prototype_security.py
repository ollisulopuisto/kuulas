"""Security hardening for docs/design/prototype/index.html (CodeQL findings)."""

from pathlib import Path

PROTOTYPE = (
    Path(__file__).resolve().parent.parent
    / "docs" / "design" / "prototype" / "index.html"
)


def test_unvalidated_dynamic_method_call_is_guarded() -> None:
    """PAGES[S.screen] must only be called when it is really a function,
    never an attacker-controlled key from the URL."""
    source = PROTOTYPE.read_text(encoding="utf8")
    idx = source.index("const page = PAGES[S.screen];")
    after = source[idx:]
    # The very next call to page() must be guarded by typeof === "function".
    assert 'typeof page === "function"' in after.split('if (!$("topbar"))')[0], (
        "page() call is not guarded by a function check"
    )


def test_theme_is_html_escaped() -> None:
    """S.theme must be escapeHtml-escaped before interpolation into HTML."""
    source = PROTOTYPE.read_text(encoding="utf8")
    assert "escapeHtml(S.theme)" in source, "S.theme is interpolated unescaped"
