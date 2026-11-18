"""The macOS menu bar copy of the in-window menu (docs/desktop.md, "The native menu bar").

The page sends its resolved menu (``ui/native-menu.js``); this module draws it as native
menus after pywebview's app menu. A native item does nothing itself: choosing it hands
``{"id", "arg"?}`` to ``run``, which sends it back to the page to run the same command as
the in-window item. Keys are shown in the title, never bound, so the keymap stays the one
owner of keys.

pywebview's own Edit and View menus are taken apart: their Cut, Copy, Paste and Select All
(the responder-chain items a text field needs) take the place of ours, and Enter
Full Screen
closes our View menu. Nothing here may stop the window: every failure is logged and the
default menus stay.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from typing import Any

from .messages import t

log = logging.getLogger("kuulas.native_menu")

MAX_ITEMS = 800
MAX_DEPTH = 3
MAX_LABEL = 120

#: Marks the top-level items this module added, so a later install can remove them.
MENU_TAG = 0x4B4D

#: Our commands that pywebview's native items replace (a text field needs them).
NATIVE_EDIT_IDS = frozenset({"edit.cut", "edit.copy", "edit.paste", "edit.select_all"})
_NATIVE_EDIT_ACTIONS = ("cut:", "copy:", "paste:", "selectAll:")

#: Right edge of the key hint inside a menu, in points.
_HINT_TAB = 300.0

#: What pywebview's menus held, kept across installs (an install moves them).
_kept: dict[str, list[Any]] = {"edit": [], "view": []}
_target: Any = None


def _text(value: Any) -> str:
    return str(value)[:MAX_LABEL] if isinstance(value, (str, int, float)) else ""


def normalize_spec(raw: Any) -> list[dict]:
    """The page's menu, cleaned: a list of ``{id, label, items}``, else ``[]``."""
    budget = [MAX_ITEMS]

    def items(entries: Any, depth: int) -> list[dict]:
        out: list[dict] = []
        if not isinstance(entries, list) or depth > MAX_DEPTH:
            return out
        for entry in entries:
            if budget[0] <= 0:
                break
            if not isinstance(entry, dict):
                continue
            kind = entry.get("kind")
            if kind == "separator":
                out.append({"kind": "separator"})
            elif kind == "submenu":
                budget[0] -= 1
                inner = items(entry.get("items"), depth + 1)
                if inner:
                    out.append(
                        {
                            "kind": "submenu",
                            "label": _text(entry.get("label")),
                            "items": inner,
                        }
                    )
            elif kind == "item":
                ident = entry.get("id")
                if not isinstance(ident, str) or not ident:
                    continue
                budget[0] -= 1
                clean = {
                    "kind": "item",
                    "id": ident[:MAX_LABEL],
                    "label": _text(entry.get("label")),
                    "keys": _text(entry.get("keys")),
                    "enabled": bool(entry.get("enabled")),
                }
                if isinstance(entry.get("arg"), str):
                    clean["arg"] = entry["arg"]
                if isinstance(entry.get("checked"), bool):
                    clean["checked"] = entry["checked"]
                out.append(clean)
        return out

    menus: list[dict] = []
    for menu in raw if isinstance(raw, list) else []:
        if not isinstance(menu, dict):
            continue
        inner = items(menu.get("items"), 1)
        if inner:
            menus.append(
                {
                    "id": _text(menu.get("id")),
                    "label": _text(menu.get("label")),
                    "items": inner,
                }
            )
    return menus


def hint_suffix(keys: str) -> str:
    """The key hint as text after the title, for when the title cannot hold a tab stop."""
    return f"  {keys}" if keys else ""


def dispatch(target: Any, sender: Any) -> None:
    """A native item was chosen: hand its command to the runner."""
    try:
        payload = json.loads(str(sender.representedObject()))
    except (TypeError, ValueError):
        return
    if isinstance(payload, dict) and isinstance(payload.get("id"), str):
        target.run(payload)


def _make_target(appkit: Any, run: Callable[[dict], None]) -> Any:
    """The object menu items call: one PyObjC class per process, runner swapped."""
    global _target  # noqa: PLW0603 - one PyObjC class per process
    if _target is None:

        class KuulasMenuTarget(appkit.NSObject):
            def invoke_(self, sender):
                dispatch(self, sender)

        _target = KuulasMenuTarget.alloc().init()
    _target.run = run
    return _target


def _titled(appkit: Any, title: str, keys: str) -> tuple[str, Any]:
    """(plain title, attributed title or None): key right-aligned if AppKit can."""
    if not keys:
        return title, None
    try:
        style = appkit.NSMutableParagraphStyle.alloc().init()
        stop = appkit.NSTextTab.alloc().initWithTextAlignment_location_options_(
            appkit.NSTextAlignmentRight, _HINT_TAB, {}
        )
        style.setTabStops_([stop])
        text = appkit.NSMutableAttributedString.alloc().initWithString_(
            f"{title}\t{keys}"
        )
        text.addAttribute_value_range_(
            appkit.NSParagraphStyleAttributeName, style, (0, len(title) + 1 + len(keys))
        )
        return title + hint_suffix(keys), text
    except Exception:  # noqa: BLE001 - any AppKit gap falls back to the plain suffix
        return title + hint_suffix(keys), None


def _leaf(appkit: Any, entry: dict, target: Any) -> Any:
    plain, attributed = _titled(appkit, entry["label"], entry["keys"])
    node = appkit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        plain, "invoke:", ""
    )
    if attributed is not None:
        node.setAttributedTitle_(attributed)
    node.setTarget_(target)
    payload = {"id": entry["id"]}
    if "arg" in entry:
        payload["arg"] = entry["arg"]
    node.setRepresentedObject_(json.dumps(payload))
    node.setEnabled_(entry["enabled"])
    if entry.get("checked"):
        node.setState_(1)
    return node


def _fill(
    appkit: Any,
    menu: Any,
    entries: list[dict],
    target: Any,
    native: list[Any],
    *,
    swap: bool = False,
) -> None:
    """``swap``: pywebview's clipboard items stand in for ours (if it had any)."""
    for entry in entries:
        kind = entry["kind"]
        if kind == "separator":
            menu.addItem_(appkit.NSMenuItem.separatorItem())
        elif kind == "submenu":
            node = appkit.NSMenuItem.alloc().init()
            node.setTitle_(entry["label"])
            sub = appkit.NSMenu.alloc().initWithTitle_(entry["label"])
            sub.setAutoenablesItems_(False)
            _fill(appkit, sub, entry["items"], target, [])
            node.setSubmenu_(sub)
            menu.addItem_(node)
        elif swap and entry["id"] in NATIVE_EDIT_IDS:
            if native:
                for kept in native:
                    _detach(kept)
                    menu.addItem_(kept)
                native.clear()
        else:
            menu.addItem_(_leaf(appkit, entry, target))


def _detach(node: Any) -> None:
    parent = node.menu()
    if parent is not None:
        parent.removeItem_(node)


def _take_pywebview_menus(main: Any) -> None:
    """Move pywebview's Edit and View contents out of the bar into ``_kept``."""
    for item in list(main.itemArray()):
        sub = item.submenu()
        if sub is None or item.tag() == MENU_TAG:
            continue
        name = str(item.title())
        if name == "Edit":
            _kept["edit"] = [
                i for i in sub.itemArray() if str(i.action()) in _NATIVE_EDIT_ACTIONS
            ]
            main.removeItem_(item)
        elif name == "View":
            _kept["view"] = list(sub.itemArray())
            main.removeItem_(item)


def _build(
    spec: list[dict],
    run: Callable[[dict], None],
    appkit: Any,
    target_factory: Callable[[Callable[[dict], None]], Any] | None,
) -> bool:
    main = appkit.NSApplication.sharedApplication().mainMenu()
    if main is None:
        return False
    target = target_factory(run) if target_factory else _make_target(appkit, run)
    for old in [i for i in main.itemArray() if i.tag() == MENU_TAG]:
        main.removeItem_(old)
    _take_pywebview_menus(main)
    position = 1  # after the app menu
    for menu in spec:
        top = appkit.NSMenuItem.alloc().init()
        top.setTitle_(menu["label"])
        top.setTag_(MENU_TAG)
        sub = appkit.NSMenu.alloc().initWithTitle_(menu["label"])
        sub.setAutoenablesItems_(False)
        native = list(_kept["edit"]) if menu["id"] == "edit" else []
        _fill(appkit, sub, menu["items"], target, native, swap=bool(native))
        if menu["id"] == "view" and _kept["view"]:
            sub.addItem_(appkit.NSMenuItem.separatorItem())
            for kept in _kept["view"]:
                _detach(kept)
                sub.addItem_(kept)
        top.setSubmenu_(sub)
        main.insertItem_atIndex_(top, position)
        position += 1
    return True


def install(
    spec: Any,
    run: Callable[[dict], None],
    *,
    platform: str | None = None,
    appkit: Any = None,
    main_thread: Callable[[Callable[[], None]], None] | None = None,
    target_factory: Callable[[Callable[[dict], None]], Any] | None = None,
) -> bool:
    """Draw ``spec`` as the native menus. True once queued; False off macOS, for an empty
    spec, or when AppKit is missing. Never raises."""
    platform = sys.platform if platform is None else platform
    if platform != "darwin":
        return False
    menus = normalize_spec(spec)
    if not menus:
        return False
    try:
        if appkit is None:
            import AppKit as appkit  # noqa: PLC0415, N813
        if main_thread is None:
            from PyObjCTools import AppHelper  # noqa: PLC0415

            main_thread = AppHelper.callAfter
    except Exception as e:  # noqa: BLE001 - a missing hook must not stop the window
        log.warning(t("log.desktop.native_menu_failed", error=str(e)))
        return False
    result = {"ok": True}

    def work() -> None:
        try:
            result["ok"] = _build(menus, run, appkit, target_factory)
        except Exception as e:  # noqa: BLE001 - the default menus stay
            result["ok"] = False
            log.warning(t("log.desktop.native_menu_failed", error=str(e)))

    main_thread(work)
    return result["ok"]
