"""The kuulas mark is in the page: the header brand and the favicon."""

import xml.etree.ElementTree as ET
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
        root = ET.parse(UI / name).getroot()
        assert root.tag.endswith("svg"), name
        assert root.get("viewBox") == "0 0 100 100", name
