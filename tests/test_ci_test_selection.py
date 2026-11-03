import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_changed_pytests import changed_test_modules, parse_shard, shard_items


def test_changed_test_modules_returns_existing_root_modules_once_in_order(
    tmp_path: Path,
):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_zeta.py").write_text("", encoding="utf-8")
    (tmp_path / "tests/test_alpha.py").write_text("", encoding="utf-8")

    assert changed_test_modules(
        ["tests/test_zeta.py", "tests/test_alpha.py", "tests/test_zeta.py"], tmp_path
    ) == ["tests/test_alpha.py", "tests/test_zeta.py"]


@pytest.mark.parametrize(
    "path",
    [
        "tests/conftest.py",
        "tests/helpers.py",
        "tests/nested/test_feature.py",
        "../outside.py",
    ],
)
def test_changed_test_modules_rejects_paths_outside_the_root_test_module_pattern(
    tmp_path: Path, path: str
):
    (tmp_path / "tests").mkdir()

    with pytest.raises(ValueError, match="root-level tests/test_\\*\\.py"):
        changed_test_modules([path], tmp_path)


def test_changed_test_modules_ignores_modules_deleted_by_the_pull_request(tmp_path: Path):
    (tmp_path / "tests").mkdir()

    assert changed_test_modules(["tests/test_removed.py"], tmp_path) == []


@pytest.mark.parametrize("spec", ["0/2", "1/0", "3/2", "1", "one/two"])
def test_parse_shard_rejects_invalid_indices(spec: str):
    with pytest.raises(ValueError, match=r"shard|Shard"):
        parse_shard(spec)


def test_shard_items_partitions_the_full_collection_without_duplicates_or_gaps():
    items = [f"test_{i}" for i in range(11)]
    shards = [shard_items(items, f"{number}/3") for number in range(1, 4)]
    selected = [item for shard, _ in shards for item in shard]

    assert sorted(selected) == sorted(items)
    assert len(selected) == len(set(selected))
    for shard, skipped in shards:
        assert set(shard).isdisjoint(skipped)
        assert sorted([*shard, *skipped]) == sorted(items)
    assert max(len(shard) for shard, _ in shards) - min(
        len(shard) for shard, _ in shards
    ) <= 1
