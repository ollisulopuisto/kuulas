#!/usr/bin/env python3
"""Lay out the Briefcase project for the tester build (WP73).

    stage_bundle.py --src <checkout> --out <stage> --wheels <folder> --label <label>

``--src`` is a clean checkout (``build_dmg.sh`` makes it with ``git archive``). The stage
folder it fills is a self-contained Briefcase project: the package, the recorder
(``kuulas_recorder``, WP12a: the app starts it as its own process through
``bundle.recorder_args``) and the UI files as source folders (Briefcase copies each into
``Resources/app``, which is where ``kuulas.paths.find_ui_dir`` looks), the icons, the
wheels, and a generated
``pyproject.toml``. The document type and its UTI live here, in :func:`render_config`:
the single place that says what Finder shows for a ``.kuulas`` folder.

(WP72's launcher app has its own plist definitions in its ``macapp`` module. Until that
is on main this file has its own copy of the identifiers; keep the two equal.)
"""

from __future__ import annotations

import argparse
import json
import shutil
import tomllib
from pathlib import Path

BUNDLE = "fi.sulopuisto"
APP_NAME = "kuulas"
FORMAL_NAME = "Kuulas"
#: Exported by the app; conforms to ``com.apple.package`` (a folder shown as a file).
UTI = "fi.sulopuisto.kuulas.project"
UTI_CONFORMS_TO = ("com.apple.package", "public.composite-content")
EXTENSION = "kuulas"
MIN_MACOS = "12.0"

#: Dependencies of the root project that the bundle gets as local wheels instead.
LOCAL = ("speechmix", "nhsx", "silencelearn")
#: Podcast apps the bundle ships as wheels although Kuulas does not depend on them: the
#: automixer runs as its own process (``automix.bundled_command``). Every wheel in the
#: wheels folder joins the requirements, so building it is what ships it.
APPS = ("automixer",)

#: Inside ``ui/``: development files that do not belong in the app.
UI_SKIP = ("tests", "biome.json", "node_modules", "package.json", "package-lock.json")

LICENSE_TEXT = """\
Kuulas. Copyright (c) 2026 Olli Sulopuisto. Free software: you can redistribute it and/or
modify it under the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any later
version. It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License (the LICENSE file of the Kuulas repository, and
https://www.gnu.org/licenses/gpl-3.0.html).

Bundled third-party software keeps its own licences; each package's licence file is in
Contents/Resources/app_packages/<package>.dist-info.

pedalboard (https://github.com/spotify/pedalboard) is licensed GPL version 3. Kuulas
loads it in its own process (through speechmix) and the bundled automixer (podcast
repository, apps/automixer) runs on it. Its licence text is in its dist-info folder and
its source is at the address above. The source of Kuulas and of the podcast packages
(speechmix, nhsx, silencelearn, automixer) is public:
https://github.com/ollisulopuisto/kuulas and https://github.com/ollisulopuisto/podcast.

ffmpeg and ffprobe (Contents/Resources/bin) are static builds from
https://ffmpeg.martin-riedl.de, licensed GPL version 3 (built with --enable-gpl
--enable-version3). They run as separate programs; their source is available from
https://ffmpeg.org and from the site above.
"""


def toml_list(items: list[str]) -> str:
    return "[" + ", ".join(json.dumps(i) for i in items) + "]"


def requirement_name(spec: str) -> str:
    """``"numpy>=2.4.2"`` -> ``"numpy"``."""
    for i, ch in enumerate(spec):
        if ch in "<>=!~;[ ":
            return spec[:i].strip().lower().replace("_", "-")
    return spec.strip().lower().replace("_", "-")


def bundle_requires(project_deps: list[str], wheels: list[Path]) -> list[str]:
    """The root project's dependencies, with the podcast packages (``LOCAL``) replaced
    by the paths of their wheels (by path, not by name: a name could be answered by an
    unrelated PyPI package), plus pywebview and the wheel-less ``proxy_tools``."""
    out = [d for d in project_deps if requirement_name(d) not in LOCAL]
    out.append("pywebview>=5")
    out.extend(str(w) for w in sorted(wheels))
    return out


def render_config(version: str, requires: list[str], wheels_dir: Path) -> str:
    """The Briefcase ``pyproject.toml`` of the stage folder."""
    conforms = toml_list(list(UTI_CONFORMS_TO))
    return f'''\
[build-system]
requires = ["briefcase"]

[tool.briefcase]
project_name = "{FORMAL_NAME}"
bundle = "{BUNDLE}"
version = "{version}"
license = "GPL-3.0+"
license-files = ["LICENSE"]
author = "Olli Sulopuisto"
author_email = "olli.sulopuisto@gmail.com"
url = "https://sulopuis.to"

[tool.briefcase.app.{APP_NAME}]
formal_name = "{FORMAL_NAME}"
description = "Multitrack spoken-word editor"
icon = "icons/kuulas"
sources = ["src/kuulas", "src/kuulas_recorder", "src/ui"]
requires = {toml_list(requires)}
test_requires = []
# Briefcase installs wheels only; proxy_tools (a pywebview dependency) publishes none.
requirement_installer_args = ["--find-links={wheels_dir}"]

[tool.briefcase.app.{APP_NAME}.macOS]
universal_build = false
# numba and llvmlite publish arm64 wheels for macOS 12 and later only (see uv.lock);
# Briefcase installs the wheels for the minimum version it is told.
min_os_version = "{MIN_MACOS}"

[tool.briefcase.app.{APP_NAME}.macOS.info]
NSMicrophoneUsageDescription = "Kuulas records narration and takes from your microphone."
NSHighResolutionCapable = true

# A project is a folder; the exported type conforms to com.apple.package so Finder shows
# it as one file and a double-click sends the app an open-files event (desktop.py).
[tool.briefcase.app.{APP_NAME}.document_type.{APP_NAME}]
extension = "{EXTENSION}"
description = "Kuulas project"
icon = "icons/kuulas"
url = "https://sulopuis.to"
macOS.CFBundleTypeRole = "Editor"
macOS.LSHandlerRank = "Owner"
macOS.LSItemContentTypes = ["{UTI}"]
macOS.UTTypeConformsTo = {conforms}
'''


def project_version(src: Path) -> tuple[str, list[str]]:
    data = tomllib.loads((src / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"]), list(data["project"]["dependencies"])


def missing_wheels(wheel_files: list[Path]) -> list[str]:
    """The podcast packages (``LOCAL``) and apps (``APPS``) with no wheel in the folder.
    Without one the build would ask PyPI for the name (an unrelated package, or none)
    or ship no automixer at all."""
    have = {w.name.split("-", 1)[0].lower().replace("_", "-") for w in wheel_files}
    return [name for name in (*LOCAL, *APPS) if name not in have]


def stage(src: Path, out: Path, wheels: Path, label: str) -> Path:
    version, deps = project_version(src)
    wheel_files = sorted(wheels.resolve().glob("*.whl"))
    missing = missing_wheels(wheel_files)
    if missing:
        problem = (f"no wheel in {wheels} for: {', '.join(missing)} "
                   "(scripts/build_wheels.sh builds them)")
        raise SystemExit(problem)
    if out.exists():
        shutil.rmtree(out)
    package = out / "src" / "kuulas"
    shutil.copytree(src / "src" / "kuulas", package,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (package / "build_label.txt").write_text(label + "\n", encoding="utf-8")
    shutil.copytree(src / "src" / "kuulas_recorder", out / "src" / "kuulas_recorder",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(src / "ui", out / "src" / "ui",
                    ignore=shutil.ignore_patterns(*UI_SKIP))
    (out / "icons").mkdir()
    shutil.copy(src / "src" / "kuulas" / "assets" / "icons" / "kuulas.icns",
                out / "icons" / "kuulas.icns")
    (out / "LICENSE").write_text(LICENSE_TEXT, encoding="utf-8")
    # Briefcase reads LICENSE as metadata and copies it nowhere; this copy is the notice
    # (GPL parts, where their sources are) inside the app: Resources/app/kuulas.
    (package / "LICENSE.txt").write_text(LICENSE_TEXT, encoding="utf-8")
    (out / "pyproject.toml").write_text(
        render_config(version, bundle_requires(deps, wheel_files), wheels.resolve()),
        encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--src", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--wheels", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    print(stage(args.src, args.out, args.wheels, args.label))


if __name__ == "__main__":
    main()
