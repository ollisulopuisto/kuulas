"""The pre-review gate agents must pass before they report ready-for-review."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "agent_gate", Path(__file__).parent.parent / "scripts" / "agent_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_files_outside_the_allowed_list_fail():
    bad = gate.out_of_scope(["src/kuulas/a.py", "pyproject.toml", "tests/test_a.py"],
                            ["src/kuulas/a.py", "tests/test_a.py"])
    assert bad == ["pyproject.toml"]


def test_globs_are_allowed():
    allowed = ["src/kuulas/locales/*.json"]
    assert gate.out_of_scope(["src/kuulas/locales/en.json"], allowed) == []


def test_files_nobody_may_touch_fail_even_if_allowed():
    bad = gate.out_of_scope(["CHANGELOG.md", "uv.lock"], ["CHANGELOG.md", "uv.lock"])
    assert bad == ["CHANGELOG.md", "uv.lock"]


def test_locale_files_must_have_the_same_keys():
    assert gate.locale_diff({"a": 1, "b": 2}, {"a": 1}) == (["b"], [])
    assert gate.locale_diff({"a": 1}, {"a": 1, "c": 3}) == ([], ["c"])


def test_a_commit_label_must_go_through_t():
    added = [
        'self.commit("closed", self.state)',
        'self.commit(t("history.closed"), self.state)',
        "self.commit(f'opened {x}', s)",
        'label = "Hello"',
    ]
    assert gate.hardcoded_labels(added) == [added[0], added[2], added[3]]


def test_a_commit_call_split_over_lines_is_still_caught():
    added = ["self.commit(", '    "closed",', "    self.state,", ")"]
    assert gate.hardcoded_labels(added) == ["self.commit("]
    assert gate.hardcoded_labels(["self.commit(", '    t("history.closed"),']) == []


def test_code_must_not_decide_by_a_translated_text():
    added = ['if label.startswith("opened "):', 'if kind == "opened":']
    assert gate.compares_text(added) == [added[0]]


def test_whole_file_reads_are_flagged():
    added = ["data, rate = sf.read(path)", "chunk = store.read(m, 0, 60 * rate)"]
    assert gate.whole_file_reads(added) == [added[0]]


def test_size_limits():
    assert gate.too_big(files=7, lines=100, max_files=6, max_lines=400) is True
    assert gate.too_big(files=6, lines=400, max_files=6, max_lines=400) is False


def test_test_files_do_not_count_toward_the_size_limit():
    numstat = [
        "300\t10\tsrc/kuulas/clipboard.py",
        "271\t0\ttests/test_clipboard.py",
        "50\t0\tui/tests/wheel.test.js",
        "5\t5\tui/wheel.js",
    ]
    files, lines = gate.size_without_tests(numstat)
    assert files == 2          # clipboard.py and wheel.js
    assert lines == 320        # 300 + 10 + 5 + 5, no test lines


def test_binary_numstat_rows_count_as_a_file_but_no_lines():
    assert gate.size_without_tests(["-\t-\tdocs/design/screenshots/a.png"]) == (1, 0)
