"""Finding outside programs (uvx, colab-transcribe, ffmpeg) when the app was started from
Finder and its PATH is only /usr/bin:/bin:/usr/sbin:/sbin."""

import os
import stat

from kuulas import toolpath

FINDER_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def make_tool(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_the_usual_install_folders_are_added_after_the_given_path(tmp_path):
    path = toolpath.search_path({"PATH": FINDER_PATH}, tmp_path).split(os.pathsep)
    assert path[:4] == ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    for wanted in ("/opt/homebrew/bin", "/usr/local/bin", str(tmp_path / ".local/bin"),
                   str(tmp_path / ".cargo/bin")):
        assert wanted in path
    assert len(path) == len(set(path))


def test_a_tool_in_the_home_bin_is_found_with_a_finder_path(tmp_path):
    tool = make_tool(tmp_path / ".local" / "bin", "kuulas-test-tool")
    found = toolpath.resolve("kuulas-test-tool", {"PATH": FINDER_PATH}, tmp_path)
    assert found == str(tool)


def test_a_missing_tool_is_none(tmp_path):
    assert toolpath.resolve("no-such-tool-xyz", {"PATH": FINDER_PATH}, tmp_path) is None


def test_a_path_with_a_slash_is_used_as_it_is_when_it_exists(tmp_path):
    tool = make_tool(tmp_path / "x", "mytool")
    assert toolpath.resolve(str(tool), {}, tmp_path) == str(tool)
    assert toolpath.resolve(str(tmp_path / "x" / "gone"), {}, tmp_path) is None


def test_the_tool_environment_has_the_wider_path_and_no_virtual_env(tmp_path):
    given = {"PATH": FINDER_PATH, "VIRTUAL_ENV": "/v", "A": "b"}
    env = toolpath.tool_env(given, tmp_path)
    assert "VIRTUAL_ENV" not in env
    assert env["A"] == "b"
    assert "/opt/homebrew/bin" in env["PATH"].split(os.pathsep)


def test_the_colab_runner_finds_a_tool_in_the_home_bin_with_a_finder_path(
        tmp_path, monkeypatch):
    import threading  # noqa: PLC0415

    from kuulas import colab_transcribe  # noqa: PLC0415

    make_tool(tmp_path / ".local" / "bin", "fake-colab-tool").write_text(
        "#!/bin/sh\necho hello from the tool\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", FINDER_PATH)
    lines: list[str] = []
    code = colab_transcribe.run_process(["fake-colab-tool"], None, lines.append,
                                        threading.Event())
    assert code == 0
    assert lines == ["hello from the tool"]


def test_the_colab_runner_still_reports_a_missing_tool_as_file_not_found(
        tmp_path, monkeypatch):
    import threading  # noqa: PLC0415

    from kuulas import colab_transcribe  # noqa: PLC0415

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", FINDER_PATH)
    try:
        colab_transcribe.run_process(["no-such-colab-tool-xyz"], None, print,
                                     threading.Event())
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")
