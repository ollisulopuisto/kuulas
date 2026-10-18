"""The kuulas mark is in the page: the header brand and the favicon."""

from pathlib import Path

UI = Path(__file__).parents[1] / "ui"


def test_index_links_the_favicon_and_shows_the_mark():
    page = (UI / "index.html").read_text()
    assert 'rel="icon"' in page
    assert 'href="/favicon.svg"' in page
    assert 'class="brand-mark"' in page
    assert 'src="/logo.svg"' in page


def test_the_mark_files_are_valid_svg_with_a_view_box():
    for name in ("logo.svg", "favicon.svg"):
        text = (UI / name).read_text()
        assert text.startswith("<svg "), name
        assert text.rstrip().endswith("</svg>"), name
        assert 'viewBox="0 0 100 100"' in text, name
