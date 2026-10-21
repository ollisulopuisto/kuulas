# ruff: noqa: E501
"""scripts/fetch_ffmpeg.sh keeps a cache copy of the binaries and falls back to it when
the download host is down (it returned 521 for hours on 2026-10-21 and failed the dmg
build). curl is replaced by a shim on PATH; no network."""

import os
import stat
import subprocess
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_ffmpeg.sh"
FAKE_TOOL = "#!/bin/sh\necho \"{name} version fake-{tag}\"\n"


def write_tool(folder: Path, name: str, tag: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(FAKE_TOOL.format(name=name, tag=tag))
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def make_zip(path: Path, name: str, tag: str) -> None:
    with zipfile.ZipFile(path, "w") as z:
        info = zipfile.ZipInfo(name)
        info.external_attr = 0o755 << 16
        z.writestr(info, FAKE_TOOL.format(name=name, tag=tag))


def shim_curl(bin_dir: Path, *, works: bool, tag: str = "net") -> None:
    """A curl that either writes a zip with the fake tool or fails like a 521."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    curl = bin_dir / "curl"
    if works:
        curl.write_text(
            "#!/bin/sh\n"
            "out=\"\"\n"
            "while [ $# -gt 0 ]; do case \"$1\" in -o) out=\"$2\"; shift;; esac; shift; done\n"
            "name=$(basename \"$out\" .zip)\n"
            f"python3 -c \"import sys,zipfile,stat; z=zipfile.ZipFile(sys.argv[1],'w'); "
            f"i=zipfile.ZipInfo(sys.argv[2]); i.external_attr=0o755<<16; "
            f"z.writestr(i, '#!/bin/sh\\necho '+sys.argv[2]+' version fake-{tag}\\n')\" "
            "\"$out\" \"$name\"\n")
    else:
        curl.write_text("#!/bin/sh\necho 'curl: (56) The requested URL returned error: 521' >&2\nexit 56\n")
    curl.chmod(0o755)


def run(tmp_path, *, cache=None, works=True, tag="net", extra_env=None):
    bin_dir = tmp_path / "bin"
    shim_curl(bin_dir, works=works, tag=tag)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    env.pop("KUULAS_FFMPEG_DIR", None)
    if cache is not None:
        env["KUULAS_FFMPEG_CACHE"] = str(cache)
    env.update(extra_env or {})
    dest = tmp_path / "dest"
    return subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT), str(dest)],  # noqa: S607
        env=env, capture_output=True, text=True, check=False), dest


def test_a_fresh_download_fills_the_cache_and_marks_it(tmp_path):
    cache = tmp_path / "cache"
    result, dest = run(tmp_path, cache=cache)
    assert result.returncode == 0, result.stderr
    assert (dest / "ffmpeg").exists()
    assert (cache / "ffmpeg").exists()
    assert (cache / "ffprobe").exists()
    assert (cache / ".fresh").exists()


def test_when_the_host_is_down_the_cached_copy_is_used(tmp_path):
    cache = tmp_path / "cache"
    write_tool(cache, "ffmpeg", "cached")
    write_tool(cache, "ffprobe", "cached")
    result, dest = run(tmp_path, cache=cache, works=False)
    assert result.returncode == 0, result.stderr
    assert "cached" in (dest / "ffmpeg").read_text()
    assert "cache" in (result.stdout + result.stderr).lower()
    assert not (cache / ".fresh").exists()


def test_a_down_host_with_no_cache_still_fails(tmp_path):
    result, _dest = run(tmp_path, cache=tmp_path / "empty-cache", works=False)
    assert result.returncode != 0


def test_without_a_cache_folder_it_behaves_as_before(tmp_path):
    result, dest = run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert (dest / "ffprobe").exists()


@pytest.mark.parametrize("works", [True, False])
def test_a_given_ffmpeg_dir_skips_everything(tmp_path, works):
    given = tmp_path / "given"
    write_tool(given, "ffmpeg", "given")
    write_tool(given, "ffprobe", "given")
    result, dest = run(tmp_path, works=works, extra_env={"KUULAS_FFMPEG_DIR": str(given)})
    assert result.returncode == 0, result.stderr
    assert "given" in (dest / "ffmpeg").read_text()


def shim_curl_fallback(bin_dir: Path) -> None:
    """The main host fails (521); any other URL serves a zip holding both tools."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    curl = bin_dir / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        "out=\"\"; url=\"\"\n"
        "while [ $# -gt 0 ]; do case \"$1\" in -o) out=\"$2\"; shift;; http*) url=\"$1\";; esac; shift; done\n"
        "case \"$url\" in *martin-riedl*) echo 'curl: (56) 521' >&2; exit 56;; esac\n"
        "python3 -c \"import sys,zipfile; z=zipfile.ZipFile(sys.argv[1],'w')\n"
        "for n in ('ffmpeg','ffprobe'):\n"
        "    i=zipfile.ZipInfo(n); i.external_attr=0o755<<16; z.writestr(i,'#!/bin/sh\\necho '+n+' version fake-fallback\\n')\" \"$out\"\n")
    curl.chmod(0o755)


def test_with_no_cache_the_release_asset_is_the_last_resort(tmp_path):
    shim_curl_fallback(tmp_path / "bin")
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
           "KUULAS_FFMPEG_FALLBACK_URL": "https://example.invalid/ffmpeg-arm64-macos.zip"}
    env.pop("KUULAS_FFMPEG_DIR", None)
    env.pop("KUULAS_FFMPEG_CACHE", None)
    dest = tmp_path / "dest"
    result = subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT), str(dest)],  # noqa: S607
        env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "fake-fallback" in (dest / "ffmpeg").read_text()
    assert "fake-fallback" in (dest / "ffprobe").read_text()
    assert "fallback" in (result.stdout + result.stderr).lower()
