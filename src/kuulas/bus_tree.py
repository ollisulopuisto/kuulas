"""Bus tree helpers for nested mixing buses, logic only.

A bus is represented as a plain dict with keys ``id``, ``parent``, ``mute`` and
``gain_db``.  The tree is a list of such dicts; order inside the list decides
sibling order.
"""

from __future__ import annotations


def _by_id(buses: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Index buses by id."""
    return {bus["id"]: bus for bus in buses}


def _children_map(
    buses: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    """Map parent id to its children in list order."""
    result: dict[str, list[dict[str, object]]] = {}
    for bus in buses:
        parent = bus["parent"]
        if parent is None:
            continue
        result.setdefault(str(parent), []).append(bus)
    return result


def depth(buses: list[dict[str, object]], bus_id: str) -> int:
    """Return the depth of ``bus_id`` (1 for a top-level bus).

    Raises ``ValueError`` for an unknown id or a cycle in the ancestry.
    """
    by_id = _by_id(buses)
    current_id = bus_id
    seen: set[str] = set()
    level = 0
    while current_id is not None:
        if current_id in seen:
            msg = f"cycle detected at bus {current_id!r}"
            raise ValueError(msg)
        seen.add(current_id)
        bus = by_id.get(current_id)
        if bus is None:
            msg = f"unknown bus id {current_id!r}"
            raise ValueError(msg)
        level += 1
        current_id = bus["parent"]  # type: ignore[assignment]
    return level


def _subtree_height(
    buses: list[dict[str, object]], bus_id: str,
    children_by_parent: dict[str, list[dict[str, object]]] | None = None,
    visiting: set[str] | None = None,
) -> int:
    """Height of the subtree rooted at ``bus_id`` (1 for a leaf)."""
    if children_by_parent is None:
        children_by_parent = _children_map(buses)
    if visiting is None:
        visiting = set()
    if bus_id in visiting:
        msg = f"cycle detected at bus {bus_id!r}"
        raise ValueError(msg)
    visiting.add(bus_id)
    children_ids = [child["id"] for child in children_by_parent.get(bus_id, [])]
    if not children_ids:
        return 1
    child_heights = [
        _subtree_height(buses, child_id, children_by_parent, visiting)
        for child_id in children_ids
    ]
    visiting.remove(bus_id)
    return 1 + max(child_heights)


def check_parent(
    buses: list[dict[str, object]],
    bus_id: str,
    parent_id: str | None,
    *,
    max_depth: int = 3,
) -> None:
    """Validate moving ``bus_id`` under ``parent_id``.

    Raises ``ValueError`` when the move would create a cycle, when the parent
    or bus is unknown, or when the bus or any descendant would end up deeper
    than ``max_depth``.  ``parent_id`` of ``None`` is always allowed.
    """
    by_id = _by_id(buses)
    if bus_id not in by_id:
        msg = f"unknown bus id {bus_id!r}"
        raise ValueError(msg)

    if parent_id is None:
        new_depth = 1
    else:
        if parent_id not in by_id:
            msg = f"unknown parent id {parent_id!r}"
            raise ValueError(msg)
        if parent_id == bus_id:
            msg = f"cycle: bus {bus_id!r} cannot be its own parent"
            raise ValueError(msg)
        children_by_parent = _children_map(buses)

        def _has_descendant(root: str, target: str, visiting: set[str]) -> bool:
            if root in visiting:
                return False
            visiting.add(root)
            for child in children_by_parent.get(root, []):
                child_id = str(child["id"])
                if child_id == target or _has_descendant(child_id, target, visiting):
                    return True
            return False

        if _has_descendant(bus_id, parent_id, set()):
            msg = f"parent {parent_id!r} would create a cycle under {bus_id!r}"
            raise ValueError(msg)
        new_depth = depth(buses, parent_id) + 1

    height = _subtree_height(buses, bus_id)
    if new_depth + height - 1 > max_depth:
        msg = f"new depth would exceed max_depth {max_depth}"
        raise ValueError(msg)


def _column_name(index: int) -> str:
    """Excel-style column name: 0 -> A, 25 -> Z, 26 -> AA."""
    chars = []
    n = index + 1
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        chars.append(chr(ord("A") + remainder))
    return "".join(reversed(chars))


def _child_suffix(depth: int, sibling_index: int) -> str:
    """Badge suffix for a child at ``depth`` (1-based) and sibling index."""
    if depth == 2:
        return str(sibling_index + 1)
    # Alternate lowercase letter, number, lowercase letter ... for deeper levels.
    if depth % 2 == 1:
        return chr(ord("a") + sibling_index)
    return str(sibling_index + 1)


def badges(buses: list[dict[str, object]]) -> dict[str, str]:
    """Return a mapping from bus id to its display badge in tree order.

    Top-level buses are labelled A, B, C ... Z, AA, AB ...; their children add
    a number, grandchildren add a lowercase letter, and deeper levels continue
    the alternating pattern.  Sibling numbers and letters follow list order.
    """
    result: dict[str, str] = {}
    children_by_parent = _children_map(buses)
    by_id = _by_id(buses)
    sibling_counters: dict[str, int] = {}

    def _assign(node_id: str, badge: str, node_depth: int) -> None:
        result[node_id] = badge
        for child in children_by_parent.get(node_id, []):
            child_id = str(child["id"])
            counter = sibling_counters.setdefault((node_id, node_depth + 1), 0)
            suffix = _child_suffix(node_depth + 1, counter)
            sibling_counters[(node_id, node_depth + 1)] = counter + 1
            _assign(child_id, badge + suffix, node_depth + 1)

    top_level_index = 0
    for bus in buses:
        if bus["parent"] is not None:
            continue
        bus_id = str(bus["id"])
        _assign(bus_id, _column_name(top_level_index), 1)
        top_level_index += 1

    # Any bus whose parent is not in the tree (orphan) appears without a badge
    # suffix and receives the next available top-level label.
    for bus in buses:
        bus_id = str(bus["id"])
        if bus_id in result:
            continue
        parent = bus["parent"]
        if parent is not None and parent not in by_id:
            _assign(bus_id, _column_name(top_level_index), 1)
            top_level_index += 1

    return result


def effective_mute(buses: list[dict[str, object]], bus_id: str) -> bool:
    """Whether ``bus_id`` or any ancestor is muted."""
    by_id = _by_id(buses)
    current_id: str | None = bus_id
    while current_id is not None:
        bus = by_id.get(current_id)
        if bus is None:
            return False
        if bus["mute"]:
            return True
        current_id = bus["parent"]  # type: ignore[assignment]
    return False


def effective_gain_db(buses: list[dict[str, object]], bus_id: str) -> float:
    """Sum of ``gain_db`` values for ``bus_id`` and its ancestors."""
    by_id = _by_id(buses)
    total = 0.0
    current_id: str | None = bus_id
    while current_id is not None:
        bus = by_id.get(current_id)
        if bus is None:
            break
        total += float(bus["gain_db"])
        current_id = bus["parent"]  # type: ignore[assignment]
    return total


def children(buses: list[dict[str, object]], bus_id: str) -> tuple[str, ...]:
    """Direct child ids of ``bus_id`` in list order."""
    return tuple(
        str(child["id"])
        for child in _children_map(buses).get(bus_id, [])
    )


def descendants(buses: list[dict[str, object]], bus_id: str) -> tuple[str, ...]:
    """All descendant ids of ``bus_id`` in depth-first list order."""
    children_by_parent = _children_map(buses)
    result: list[str] = []

    def _walk(node_id: str) -> None:
        for child in children_by_parent.get(node_id, []):
            child_id = str(child["id"])
            result.append(child_id)
            _walk(child_id)

    _walk(bus_id)
    return tuple(result)
