"""kuulas_recorder stands alone: nothing from the editor, no audio in the supervisor."""

import ast
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "src" / "kuulas_recorder"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
    return out


def test_recorder_imports_nothing_from_the_editor():
    allowed_third_party = {"numpy", "sounddevice"}
    for path in sorted(PKG.glob("*.py")):
        for mod in imported_modules(path):
            top = mod.split(".")[0]
            assert top != "kuulas", f"{path.name} imports {mod}"
            if top == "kuulas_recorder" or top in sys.stdlib_module_names:
                continue
            assert top in allowed_third_party, f"{path.name} imports {mod}"


def test_supervisor_and_client_never_load_portaudio():
    code = (
        "import sys\n"
        "import kuulas_recorder.supervisor, kuulas_recorder.client, kuulas_recorder.cli\n"
        "bad = [m for m in sys.modules if m == 'sounddevice' or m == 'kuulas'"
        " or m.startswith('kuulas.')]\n"
        "print(bad)\n"
    )
    out = subprocess.run(  # noqa: S603 - this Python, fixed code
        [sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def test_the_package_is_in_the_wheel_and_has_a_console_script():
    import tomllib  # noqa: PLC0415

    data = tomllib.loads((PKG.parents[1] / "pyproject.toml").read_text())
    assert "src/kuulas_recorder" in data["tool"]["hatch"]["build"]["targets"]["wheel"][
        "packages"]
    assert data["project"]["scripts"]["kuulas-recorder"] == "kuulas_recorder.cli:main"
