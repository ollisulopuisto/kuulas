"""The app icon files and the mark's single source (scripts/make_icons.py)."""

import importlib.util
import struct
from pathlib import Path

ROOT = Path(__file__).parents[1]
ICONS = ROOT / "src" / "kuulas" / "assets" / "icons"
SIZES = (16, 32, 48, 64, 128, 256, 512, 1024)


def load_script():
    path = ROOT / "scripts" / "make_icons.py"
    spec = importlib.util.spec_from_file_location("make_icons", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    return struct.unpack(">II", data[16:24])


def test_the_png_set_has_every_size():
    for size in SIZES:
        assert png_size(ICONS / f"kuulas-{size}.png") == (size, size)


def test_windows_icon_has_the_standard_sizes():
    data = (ICONS / "kuulas.ico").read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1)
    assert count >= 4


def test_macos_icon_is_an_icns_file():
    assert (ICONS / "kuulas.icns").read_bytes()[:4] == b"icns"


def test_the_app_svgs_are_what_the_script_draws():
    script = load_script()
    assert (ROOT / "ui" / "logo.svg").read_text() == script.mark_svg(9, 1.5) + "\n"
    assert (ROOT / "ui" / "favicon.svg").read_text() == script.mark_svg(7, 1.5) + "\n"
