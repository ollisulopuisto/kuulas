"""A packaged app must carry and exercise its own uv/uvx, not borrow developer tools."""

import pytest

from kuulas import bundle, selftest


def test_packaged_selftest_refuses_missing_uv_even_when_host_has_it(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(bundle, "resources_dir", lambda _file: tmp_path)
    with pytest.raises(selftest.SelftestError, match="uv"):
        selftest.check_tools()


def test_packaged_selftest_runs_both_embedded_tools_with_finder_path(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(bundle, "resources_dir", lambda _file: tmp_path)
    folder = tmp_path / "bin"
    folder.mkdir()
    for name in ("uv", "uvx"):
        tool = folder / name
        tool.write_text(f"#!/bin/sh\necho '{name} bundled-test'\n")
        tool.chmod(0o755)
    result = selftest.check_tools()
    assert "uv bundled-test" in result
    assert "uvx bundled-test" in result
