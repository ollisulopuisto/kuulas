"""The recent projects list: merge, live filter, display names, sorting.

Pure functions over lists of path strings, most recent first: adding a
project moves it to the front and drops the oldest overflow, a
caller-supplied ``exists`` filters the dead paths out, and the display
names the "Other projects" list shows drop the parent and the ``.kuulas``
suffix. No function touches its input.
"""

import pytest

from kuulas.recent_projects import (
    display_name,
    live_recent,
    merge_recent,
    sort_by_name,
)

# -- merge_recent -------------------------------------------------------------


def test_merge_recent_puts_the_new_path_first_and_keeps_the_rest():
    result = merge_recent(["/a/Two.kuulas", "/a/Three.kuulas"], "/a/One.kuulas")
    assert result == ["/a/One.kuulas", "/a/Two.kuulas", "/a/Three.kuulas"]


def test_merge_recent_removes_an_earlier_copy_compared_by_normpath():
    existing = ["/a/One.kuulas/", "/a/Two.kuulas"]
    result = merge_recent(existing, "/a/One.kuulas")
    assert result == ["/a/One.kuulas", "/a/Two.kuulas"]


def test_merge_recent_removes_every_earlier_copy_whatever_the_spelling():
    existing = ["/a/One.kuulas/", "/b/Other", "/a/./One.kuulas"]
    result = merge_recent(existing, "/a/One.kuulas")
    assert result == ["/a/One.kuulas", "/b/Other"]


def test_merge_recent_leaves_other_paths_alone():
    existing = ["/a/One", "/a/One Two"]
    result = merge_recent(existing, "/a/One Two")
    assert result == ["/a/One Two", "/a/One"]


def test_merge_recent_cuts_to_the_limit_including_the_new_path():
    existing = [f"/a/P{n:02d}" for n in range(20)]
    result = merge_recent(existing, "/a/New", limit=5)
    assert result == ["/a/New", "/a/P00", "/a/P01", "/a/P02", "/a/P03"]
    result = merge_recent(existing, "/a/New", limit=21)
    assert len(result) == 21


def test_merge_recent_with_limit_one_keeps_only_the_new_path():
    existing = ["/a/One", "/a/Two"]
    assert merge_recent(existing, "/a/New", limit=1) == ["/a/New"]


def test_merge_recent_default_limit_is_20():
    existing = [f"/a/P{n:02d}" for n in range(30)]
    result = merge_recent(existing, "/a/New")
    assert len(result) == 20
    assert result[0] == "/a/New"
    assert result[-1] == "/a/P18"


def test_merge_recent_refuses_a_limit_below_one():
    with pytest.raises(ValueError, match="limit"):
        merge_recent([], "/a/New", limit=0)
    with pytest.raises(ValueError, match="limit"):
        merge_recent([], "/a/New", limit=-3)


def test_merge_recent_returns_a_new_list_and_never_touches_existing():
    existing = ["/a/Two.kuulas", "/a/One.kuulas"]
    result = merge_recent(existing, "/a/One.kuulas")
    assert existing == ["/a/Two.kuulas", "/a/One.kuulas"]
    assert result == ["/a/One.kuulas", "/a/Two.kuulas"]
    assert result is not existing


# -- live_recent --------------------------------------------------------------


def test_live_recent_keeps_only_accepted_paths_in_their_order():
    paths = ["/a/One", "/b/Two", "/c/Three"]
    result = live_recent(paths, lambda p: p != "/b/Two")
    assert result == ["/a/One", "/c/Three"]


def test_live_recent_deduplicates_by_normpath_keeping_the_first_spelling():
    paths = ["/a/One/", "/a/One", "/b/Two"]
    result = live_recent(paths, lambda _p: True)
    assert result == ["/a/One/", "/b/Two"]


def test_live_recent_passes_the_given_spelling_to_exists_once_each():
    seen: list[str] = []

    def exists(path: str) -> bool:
        seen.append(path)
        return True

    result = live_recent(["/a/One", "/b/Two", "/a/One/"], exists)
    assert result == ["/a/One", "/b/Two"]
    assert seen == ["/a/One", "/b/Two"]


def test_live_recent_with_nothing_accepted_gives_an_empty_list():
    assert live_recent(["/a/One", "/b/Two"], lambda _p: False) == []


def test_live_recent_with_an_empty_list_is_empty():
    assert live_recent([], lambda _p: True) == []


def test_live_recent_never_touches_its_input():
    paths = ["/a/One", "/a/One/"]
    live_recent(paths, lambda _p: True)
    assert paths == ["/a/One", "/a/One/"]


# -- display_name ------------------------------------------------------------


def test_display_name_drops_the_parent_and_a_trailing_kuulas():
    assert display_name("/a/b/Vikasietotila s13e04.kuulas/") == (
        "Vikasietotila s13e04")


def test_display_name_keeps_a_folder_without_the_suffix_as_it_is():
    assert display_name("/a/b/Haaraputki/") == "Haaraputki"
    assert display_name("/a/b/Haaraputki") == "Haaraputki"


def test_display_name_of_a_bare_name_has_no_parent_to_drop():
    assert display_name("Vikasietotila s13e04.kuulas") == "Vikasietotila s13e04"


def test_display_name_of_an_empty_path_is_empty():
    assert display_name("") == ""


def test_display_name_strips_only_one_trailing_suffix():
    assert display_name("/a/Backup.kuulas.kuulas") == "Backup.kuulas"


def test_display_name_keeps_finnish_letters():
    assert display_name("/a/Äänite ö.kuulas") == "Äänite ö"


# -- sort_by_name -------------------------------------------------------------


def test_sort_by_name_sorts_case_insensitively_by_display_name():
    paths = ["/b/banana.kuulas", "/a/Apple.kuulas", "/c/cherry"]
    assert sort_by_name(paths) == [
        "/a/Apple.kuulas", "/b/banana.kuulas", "/c/cherry"]


def test_sort_by_name_breaks_ties_by_the_full_path():
    paths = ["/b/Same.kuulas", "/a/Same.kuulas"]
    assert sort_by_name(paths) == ["/a/Same.kuulas", "/b/Same.kuulas"]


def test_sort_by_name_ignores_the_kuulas_suffix_when_comparing():
    paths = ["/a/Beta.kuulas", "/b/Alpha"]
    assert sort_by_name(paths) == ["/b/Alpha", "/a/Beta.kuulas"]


def test_sort_by_name_keeps_finnish_letters():
    paths = ["/a/Öljy.kuulas", "/b/Kaura.kuulas"]
    assert sort_by_name(paths) == ["/b/Kaura.kuulas", "/a/Öljy.kuulas"]


def test_sort_by_name_returns_a_new_list_and_never_touches_its_input():
    paths = ["/b/Two.kuulas", "/a/One.kuulas"]
    result = sort_by_name(paths)
    assert paths == ["/b/Two.kuulas", "/a/One.kuulas"]
    assert result == ["/a/One.kuulas", "/b/Two.kuulas"]
    assert result is not paths


def test_sort_by_name_of_an_empty_list_is_empty():
    assert sort_by_name([]) == []
