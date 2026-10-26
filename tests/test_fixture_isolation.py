"""The per-user files used by tests stay private and cheap to allocate."""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path


def test_private_user_state_is_isolated_in_nested_pytest(tmp_path):
    """Exercise the repository conftest in a fresh pytest session."""
    nested_dir = Path(__file__).parent / f".fixture-isolation-{uuid.uuid4().hex}"
    nested_dir.mkdir()
    report = tmp_path / "paths.jsonl"
    module = nested_dir / "test_generated.py"
    module.write_text(
        '''
import json
import os
from pathlib import Path


def _check_paths():
    names = {
        "clipboard": "KUULAS_CLIPBOARD_FILE",
        "recents": "KUULAS_RECENTS_FILE",
        "settings": "KUULAS_SETTINGS_FILE",
        "series": "KUULAS_SERIES_DIR",
        "view_memory": "KUULAS_VIEW_MEMORY_FILE",
        "colab": "KUULAS_COLAB_TOKEN",
    }
    paths = {name: Path(os.environ[key]) for name, key in names.items()}
    leaf_dirs = {
        name: path if name == "series" else path.parent
        for name, path in paths.items()
    }
    case_dirs = {path.parent for path in leaf_dirs.values()}
    assert len(case_dirs) == 1
    case_dir = case_dirs.pop()
    root = case_dir.parent
    assert root.parent == Path(os.environ["PYTEST_TMPDIR"])
    assert root.name.startswith("private-user-state")
    assert all(path.is_relative_to(root) for path in leaf_dirs.values())
    assert len(set(leaf_dirs.values())) == 6

    for name, path in leaf_dirs.items():
        if name == "colab":
            assert json.loads(path.joinpath("token.json").read_text()) == {
                "refresh_token": "test"
            }
        else:
            assert list(path.iterdir()) == []
    with Path(os.environ["FIXTURE_PATH_REPORT"]).open("a") as report:
        report.write(
            json.dumps({name: str(path) for name, path in paths.items()}) + "\\n"
        )


def test_first_generated_case():
    _check_paths()


def test_second_generated_case():
    _check_paths()
''',
        encoding="utf-8",
    )
    (nested_dir / "conftest.py").write_text(
        'import os\nimport pytest\n\n'
        '@pytest.fixture(autouse=True)\n'
        'def _expose_tmpdir(tmp_path_factory, monkeypatch):\n'
        '    monkeypatch.setenv("PYTEST_TMPDIR", str(tmp_path_factory.getbasetemp()))\n',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["FIXTURE_PATH_REPORT"] = str(report)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for key in (
        "KUULAS_CLIPBOARD_FILE",
        "KUULAS_RECENTS_FILE",
        "KUULAS_SETTINGS_FILE",
        "KUULAS_SERIES_DIR",
        "KUULAS_VIEW_MEMORY_FILE",
        "KUULAS_COLAB_TOKEN",
    ):
        env.pop(key, None)
    try:
        # The executable and test module are fixed by this test, not user input.
        result = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                f"--rootdir={Path(__file__).parents[1]}",
                f"--confcutdir={Path(__file__).parent}",
                str(module),
            ],
            cwd=Path(__file__).parents[1],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        for path in nested_dir.iterdir():
            if path.is_dir():
                for child in path.iterdir():
                    child.unlink()
                path.rmdir()
            else:
                path.unlink()
        nested_dir.rmdir()

    assert result.returncode == 0, result.stdout + result.stderr
    rows = [json.loads(line) for line in report.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0] != rows[1]
    roots = {
        Path(value).parent.parent.parent
        for name, value in rows[0].items()
        if name != "series"
    }
    roots.update(Path(rows[0]["series"]).parent.parent for _ in (0,))
    assert len(roots) == 1
    root = roots.pop()
    numbered_roots = [
        path for path in root.parent.glob("private-user-state*") if not path.is_symlink()
    ]
    assert numbered_roots == [root]
