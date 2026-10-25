"""The Briefcase project laid out for the tester build (WP73): the generated config, the
document type and the files staged. No Briefcase run."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

scripts_dir = Path(__file__).parent.parent / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

import stage_bundle  # noqa: E402

from kuulas import macapp  # noqa: E402

REPO = Path(__file__).parent.parent


def wheels(tmp_path: Path) -> Path:
    folder = tmp_path / "wheels"
    folder.mkdir()
    for name in ("speechmix-1-py3-none-any.whl", "nhsx-1-py3-none-any.whl",
                 "silencelearn-1-py3-none-any.whl", "automixer-1-py3-none-any.whl",
                 "proxy_tools-0.1.0-py3-none-any.whl"):
        (folder / name).write_text("", encoding="utf-8")
    return folder


def test_local_dependencies_are_replaced_by_wheel_paths(tmp_path):
    got = stage_bundle.bundle_requires(
        ["speechmix", "nhsx", "numpy>=2.4.2", "fastapi>=0.118.0"],
        sorted(wheels(tmp_path).glob("*.whl")))
    names = [stage_bundle.requirement_name(r) for r in got]
    assert "speechmix" not in got
    assert got[:2] == ["numpy>=2.4.2", "fastapi>=0.118.0"]
    assert "pywebview>=5" in got
    assert sum(r.endswith("speechmix-1-py3-none-any.whl") for r in got) == 1
    assert sum(r.endswith("nhsx-1-py3-none-any.whl") for r in got) == 1
    assert names.count("numpy") == 1


def test_requirement_names():
    assert stage_bundle.requirement_name("python-multipart>=0.0.20") == "python-multipart"
    assert stage_bundle.requirement_name("Foo_Bar[extra]>=1") == "foo-bar"
    assert stage_bundle.requirement_name("nhsx") == "nhsx"


def config(tmp_path):
    text = stage_bundle.render_config("26.10.19.6", ["numpy"], tmp_path)
    return tomllib.loads(text)["tool"]["briefcase"]


def test_the_config_is_valid_toml_with_the_bundle_identity(tmp_path):
    briefcase = config(tmp_path)
    app = briefcase["app"]["kuulas"]
    assert briefcase["bundle"] == "fi.sulopuisto"
    assert briefcase["version"] == "26.10.19.6"
    assert briefcase["license"] == "GPL-3.0+"
    assert briefcase["license-files"] == ["LICENSE"]
    assert app["formal_name"] == "Kuulas"
    # the recorder (WP12a) is its own package: the app starts it as its own process
    assert app["sources"] == ["src/kuulas", "src/kuulas_recorder", "src/ui"]
    assert app["requires"] == ["numpy"]


def test_the_document_type_is_a_package_that_the_app_owns(tmp_path):
    doc = config(tmp_path)["app"]["kuulas"]["document_type"]["kuulas"]
    assert doc["extension"] == "kuulas"
    assert doc["macOS"]["CFBundleTypeRole"] == "Editor"
    # "Owner" is what makes Briefcase write an *exported* type declaration.
    assert doc["macOS"]["LSHandlerRank"] == "Owner"
    assert doc["macOS"]["LSItemContentTypes"] == ["fi.sulopuisto.kuulas.project"]
    assert "com.apple.package" in doc["macOS"]["UTTypeConformsTo"]


def test_identifiers_equal_the_wp72_launcher_apps(tmp_path):
    # Two apps declare the same type; if they disagreed, Finder would use one at random.
    assert f"{stage_bundle.BUNDLE}.{stage_bundle.APP_NAME}" == macapp.BUNDLE_ID
    assert stage_bundle.UTI == macapp.UTI
    assert stage_bundle.EXTENSION == macapp.EXTENSION
    exported = macapp.plist_keys()["UTExportedTypeDeclarations"][0]
    assert tuple(exported["UTTypeConformsTo"]) == stage_bundle.UTI_CONFORMS_TO


def test_minimum_macos_is_what_numba_wheels_need(tmp_path):
    assert config(tmp_path)["app"]["kuulas"]["macOS"]["min_os_version"] == "12.0"


def test_the_microphone_reason_is_declared(tmp_path):
    info = config(tmp_path)["app"]["kuulas"]["macOS"]["info"]
    assert info["NSMicrophoneUsageDescription"]


def test_stage_lays_out_a_self_contained_project(tmp_path):
    out = stage_bundle.stage(REPO, tmp_path / "stage", wheels(tmp_path), "v1+abc")
    assert (out / "src/kuulas/__main__.py").is_file()
    assert (out / "src/kuulas/build_label.txt").read_text().strip() == "v1+abc"
    assert (out / "src/ui/index.html").is_file()
    assert (out / "src/kuulas_recorder/__main__.py").is_file()
    assert (out / "src/kuulas_recorder/client.py").is_file()
    assert (out / "icons/kuulas.icns").is_file()
    assert (out / "LICENSE").is_file()
    assert not (out / "src/ui/tests").exists()
    assert not (out / "src/ui/biome.json").exists()
    assert not list(out.rglob("__pycache__"))
    parsed = tomllib.loads((out / "pyproject.toml").read_text())
    version = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["version"]
    assert parsed["tool"]["briefcase"]["version"] == version


def test_every_podcast_path_dependency_is_shipped_as_a_wheel():
    """A podcast package added to pyproject (a ``../podcast`` path source) must also be
    built by build_wheels.sh, swapped for its wheel by stage_bundle and imported by the
    in-app selftest, or the .dmg starts without it (silencelearn, 2026-10-21)."""
    from kuulas import selftest  # noqa: PLC0415

    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    sources = project["tool"]["uv"]["sources"]
    podcast = sorted(name for name, spec in sources.items()
                     if str(spec.get("path", "")).startswith("../podcast/"))
    assert "silencelearn" in podcast
    built = (REPO / "scripts" / "build_wheels.sh").read_text(encoding="utf-8")
    loop = next(line for line in built.splitlines() if line.startswith("for pkg in "))
    for name in podcast:
        assert name in stage_bundle.LOCAL, name
        assert f" {name}" in loop, name
        assert name in selftest.LIBRARIES, name


def test_the_automixer_app_is_built_staged_and_selftested():
    """The automixer is no dependency of Kuulas (the editor never imports it) but the
    bundle ships it: build_wheels.sh builds it from ``apps/``, its wheel joins the
    requirements by path, and the selftest runs its ``--help`` from the bundle."""
    from kuulas import selftest  # noqa: PLC0415

    assert stage_bundle.APPS == ("automixer",)
    built = (REPO / "scripts" / "build_wheels.sh").read_text(encoding="utf-8")
    loop = next(line for line in built.splitlines() if line.startswith("for app in "))
    for name in stage_bundle.APPS:
        assert f" {name}" in loop, name
        assert name in selftest.CHECKS, name
    assert '"$src/apps/$app"' in built


def test_the_automixer_wheel_is_a_requirement_by_path(tmp_path):
    got = stage_bundle.bundle_requires(["numpy"], sorted(wheels(tmp_path).glob("*.whl")))
    assert sum(r.endswith("automixer-1-py3-none-any.whl") for r in got) == 1


def test_stage_refuses_a_wheels_folder_without_a_podcast_wheel(tmp_path):
    folder = wheels(tmp_path)
    (folder / "automixer-1-py3-none-any.whl").unlink()
    with pytest.raises(SystemExit, match="automixer"):
        stage_bundle.stage(REPO, tmp_path / "stage", folder, "v1+abc")


def test_the_bundle_licence_names_the_gpl_parts():
    text = stage_bundle.LICENSE_TEXT
    assert "pedalboard" in text
    assert "GPL" in text
    assert "automixer" in text


AUTOMIXER_PYPROJECT = '''[project]
name = "automixer"
dependencies = [
    "speechmix",
    # Apple Silicon only: the TUI and the in-memory mixer use mlx.
    "mlx>=0.30.6; sys_platform == 'darwin'",
    "numpy>=2.4.2",
    "textual>=8.0.0",
]

[tool.uv.sources]
speechmix = { workspace = true }
'''


def test_the_bundled_automixer_drops_mlx_and_textual():
    """mlx publishes no wheel for the bundle's macOS 12 target (the 2026-10-21 local
    build failed on it) and only the TUI and the in-memory route use mlx and textual;
    Kuulas runs the folder route. The trim edits a copy, never the podcast checkout."""
    import trim_deps  # noqa: PLC0415

    text = trim_deps.trim(AUTOMIXER_PYPROJECT, trim_deps.UNUSED)
    deps = tomllib.loads(text)["project"]["dependencies"]
    assert deps == ["speechmix", "numpy>=2.4.2"]
    assert "uv" not in tomllib.loads(text).get("tool", {})  # no workspace outside it
    built = (REPO / "scripts" / "build_wheels.sh").read_text(encoding="utf-8")
    assert "trim_deps.py" in built


def test_trim_is_a_no_op_once_the_podcast_makes_them_extras(capsys):
    import trim_deps  # noqa: PLC0415

    text = '[project]\nname = "x"\ndependencies = [\n    "numpy",\n]\n'
    assert tomllib.loads(trim_deps.trim(text, ("mlx",)))["project"]["dependencies"] == [
        "numpy"]
    assert "mlx" in capsys.readouterr().err  # said, so the trim can be retired


def test_the_licence_notice_ships_inside_the_app(tmp_path):
    """Briefcase uses ``LICENSE`` as metadata only: the 2026-10-21 build had it nowhere in
    Kuulas.app or the .dmg. A copy in the package lands in Resources/app/kuulas."""
    out = stage_bundle.stage(REPO, tmp_path / "stage", wheels(tmp_path), "v1+abc")
    notice = (out / "src/kuulas/LICENSE.txt").read_text(encoding="utf-8")
    assert notice == stage_bundle.LICENSE_TEXT
