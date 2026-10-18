"""Draw the kuulas mark and write the app icons (run on macOS, by hand).

    uv run --with resvg-py --with pillow python scripts/make_icons.py

This is the single source of the mark: it writes ``ui/logo.svg`` (nine bars),
``ui/favicon.svg`` (seven bars) and, in ``src/kuulas/assets/icons/``, the PNG set,
``kuulas.ico`` (Windows) and ``kuulas.icns`` (macOS, needs ``iconutil``). The
mark: a disc of vertical bars (a waveform), one bar missing, with a round hole
whose edges sit in the gaps between bars so no bar gets a sliver.
"""

from __future__ import annotations

import io
import math
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
ICONS = ROOT / "src" / "kuulas" / "assets" / "icons"
GREEN = "#8CBF3F"  # apple green, a placeholder until the UI tokens carry it
DEEP = "#1B2E1D"  # the icon's background
SIZES = (16, 32, 48, 64, 128, 256, 512, 1024)


def _bars_and_hole(n: int, rscale: float, cy: float, radius: float = 46.0):
    pitch = 92 / n
    width = pitch * 0.66
    missing = n // 2 + 1

    def centre(i: int) -> float:
        return 4 + pitch * (i + 0.5)

    bars = "".join(
        f'<rect x="{centre(i) - width / 2:.2f}" y="{50 - h / 2:.2f}" width="{width:.2f}" '
        f'height="{h:.2f}" rx="{width / 2:.2f}"/>'
        for i in range(n) if i != missing
        for h in [2 * math.sqrt(radius**2 - (centre(i) - 50) ** 2) * 0.94])
    hole = f'<circle cx="{centre(missing):.2f}" cy="{cy}" r="{rscale * pitch:.2f}"/>'
    return bars, hole


def mark_svg(n: int, rscale: float = 1.5, cy: float = 60, fill: str = GREEN) -> str:
    """The mark on a transparent 100 x 100 canvas."""
    bars, hole = _bars_and_hole(n, rscale, cy)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs>'
            '<mask id="m"><rect width="100" height="100" fill="#fff"/>'
            f'{hole}</mask></defs>'
            f'<g mask="url(#m)" fill="{fill}">{bars}</g></svg>')


def icon_svg(n: int = 9, margin: float = 0.0) -> str:
    """The mark on a rounded square, for app icons. `margin` (0 to 0.2) is the
    transparent border macOS expects around the square."""
    bars, hole = _bars_and_hole(n, 1.5, 60)
    side = 1024 * (1 - 2 * margin)
    offset = 1024 * margin
    scale = side * 0.66 / 100
    shift = offset + side * 0.17
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">'
            f'<rect x="{offset}" y="{offset}" width="{side}" height="{side}" '
            f'rx="{side * 0.2237:.1f}" fill="{DEEP}"/>'
            '<defs><mask id="m"><rect width="100" height="100" fill="#fff"/>'
            f'{hole}</mask></defs>'
            f'<g transform="translate({shift:.1f} {shift:.1f}) scale({scale:.3f})">'
            f'<g mask="url(#m)" fill="{GREEN}">{bars}</g></g></svg>')


def main() -> None:
    import resvg_py  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    (ROOT / "ui" / "logo.svg").write_text(mark_svg(9, 1.5) + "\n")
    (ROOT / "ui" / "favicon.svg").write_text(mark_svg(7, 1.5) + "\n")
    ICONS.mkdir(parents=True, exist_ok=True)

    def render(svg: str, px: int) -> Image.Image:
        svg = svg.replace('viewBox="0 0 1024 1024"',
                          f'width="{px}" height="{px}" viewBox="0 0 1024 1024"', 1)
        data = bytes(resvg_py.svg_to_bytes(svg_string=svg))
        return Image.open(io.BytesIO(data)).convert("RGBA")

    plain = icon_svg(9, 0.0)
    (ICONS / "kuulas-icon.svg").write_text(plain + "\n")
    for size in SIZES:
        render(plain, size).save(ICONS / f"kuulas-{size}.png")
    ico_sizes = [(s, s) for s in (16, 32, 48, 64, 128, 256)]
    render(plain, 256).save(ICONS / "kuulas.ico", sizes=ico_sizes)

    if not Path("/usr/bin/iconutil").exists():
        print("iconutil not found: kuulas.icns not written (run this on macOS)")
        return
    mac = icon_svg(9, 0.098)  # Apple's template leaves about 10 percent around the square
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "kuulas.iconset"
        iconset.mkdir()
        for base in (16, 32, 128, 256, 512):
            render(mac, base).save(iconset / f"icon_{base}x{base}.png")
            render(mac, base * 2).save(iconset / f"icon_{base}x{base}@2x.png")
        out = str(ICONS / "kuulas.icns")
        subprocess.run(["/usr/bin/iconutil", "-c", "icns", str(iconset), "-o", out],  # noqa: S603
                       check=True)
    render(mac, 512).save(ICONS / "kuulas-dock.png")


if __name__ == "__main__":
    main()
