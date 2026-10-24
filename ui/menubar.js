// The in-window menu bar (FIRST CUT: structure and behaviour are settled, the
// visual design is for the designer to review). Driven by menu-model.js, so an
// item is greyed (aria-disabled, still visible, its key still shown) when its
// command cannot apply, shows the user's current key, and swaps to its alternate
// while Alt or Shift is held. No animation: items change in place.
//
// Pattern: WAI-ARIA menubar. Left/Right between menus, Up/Down between items,
// Enter or Space runs, Right opens a submenu and Left or Esc closes it, Esc closes
// the menu and returns to the bar. Disabled items are focusable (they teach) but
// do nothing. No mnemonics.

import { flashTop } from "./menu-flash.js";
import { isHoverPointer, movingToward, rowHover, topHover } from "./menu-hover.js";
import { findItem, fitMenus, moveItem, moveMenu, overflowMenu } from "./menu-model.js";

/** How long a menu title stays lit when a key ran one of its commands. */
const FLASH_MS = 260;

export function createMenubar({ root, getMenus, run, onHint, t, search = null }) {
  // open: whether a menu is dropped down; top: which; item/sub: positions inside it.
  const at = { open: false, top: 0, item: -1, subOpen: false, sub: -1 };
  let wantFocus = false; // one-shot: focus the current item after the next render
  let shown = Infinity; // how many top-level menus fit; the rest sit in the "…" menu
  let hoverTimer = null; // a submenu opening or closing that waits for the pointer to rest
  let lastPointer = null; // where the mouse was, for the diagonal-movement grace

  function cancelHover() {
    clearTimeout(hoverTimer);
    hoverTimer = null;
  }

  root.setAttribute("role", "menubar");
  root.setAttribute("aria-label", t("menu.bar"));

  /** The bar as shown: the menus that fit, then "…" holding the others. */
  function effective() {
    const all = getMenus();
    if (shown >= all.length) return all;
    return [...all.slice(0, shown), overflowMenu(all.slice(shown), t("menu.more"))];
  }

  /** Measure the titles in the bar and the room for them; sets `shown`. */
  function fit() {
    const spacer = root.parentElement?.querySelector(".spacer");
    const available = root.offsetWidth + (spacer?.offsetWidth ?? 0);
    const widths = [...root.querySelectorAll(".menu-title")].map((el) => el.offsetWidth);
    const gap = Number.parseFloat(getComputedStyle(root).columnGap) || 0;
    const more = root.querySelector(".menu-more");
    shown = fitMenus(widths, available, { gap, overflowWidth: more?.offsetWidth ?? 40 });
  }

  function render() {
    // First every menu, to measure; if they do not all fit, once more with "…".
    const focusAfter = wantFocus || root.contains(document.activeElement);
    wantFocus = false;
    shown = Infinity;
    draw();
    fit();
    if (shown < getMenus().length) draw();
    if (focusAfter) focusCurrent();
  }

  function draw() {
    const menus = effective();
    if (at.top >= menus.length) at.top = menus.length - 1;
    root.replaceChildren();
    menus.forEach((menu, index) => {
      const cell = document.createElement("div");
      cell.className = "menu-top";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "menu-title";
      button.setAttribute("role", "menuitem");
      button.setAttribute("aria-haspopup", "menu");
      button.setAttribute("aria-expanded", String(at.open && at.top === index));
      button.tabIndex = at.top === index ? 0 : -1;
      button.dataset.pos = `${index}`;
      button.textContent = menu.label;
      if (menu.id === "overflow") {
        button.classList.add("menu-more");
        button.setAttribute("aria-label", menu.label);
        button.textContent = "…";
      }
      cell.append(button);
      if (at.open && at.top === index) cell.append(list(menu.items, false));
      root.append(cell);
    });
  }

  function list(items, isSub) {
    const ul = document.createElement("ul");
    ul.className = isSub ? "menu-list submenu" : "menu-list";
    ul.setAttribute("role", "menu");
    items.forEach((item, index) => {
      const li = document.createElement("li");
      li.setAttribute("role", "none");
      if (item.kind === "separator") {
        li.setAttribute("role", "separator");
        if (item.caption) {
          li.className = "menu-caption";
          li.textContent = item.caption;
        }
        ul.append(li);
        return;
      }
      if (item.kind === "search" && search) {
        // WP75: the Help menu's first item is a text field (command-search-ui.js). Its own keys
        // are the field's; the bar's handler below leaves them alone.
        li.className = "menu-search";
        search.element.dataset.pos = `${isSub ? "s" : "i"}${index}`;
        li.append(search.element);
        ul.classList.add("has-search");
        ul.append(li);
        return;
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = "menu-item";
      button.setAttribute("role", "menuitem");
      button.tabIndex = -1;
      button.dataset.pos = `${isSub ? "s" : "i"}${index}`;
      const name = document.createElement("span");
      name.textContent = item.label;
      button.append(name);
      if (item.kind === "submenu") {
        button.setAttribute("aria-haspopup", "menu");
        button.setAttribute("aria-expanded", String(at.subOpen && at.item === index));
        const arrow = document.createElement("span");
        arrow.setAttribute("aria-hidden", "true");
        arrow.textContent = "›";
        button.append(arrow);
      } else {
        button.setAttribute("aria-disabled", String(!item.enabled));
        if (item.checked !== undefined) {
          button.setAttribute("role", "menuitemcheckbox");
          button.setAttribute("aria-checked", String(item.checked));
        }
        if (item.alternate) button.dataset.alternate = "";
        button.title = item.tooltip;
        if (item.keys) {
          const kbd = document.createElement("kbd");
          kbd.textContent = item.keys;
          button.append(kbd);
        }
        button.dataset.hint = item.tooltip;
        button.dataset.command = item.id; // F1 opens help for it (help-panel.js)
      }
      li.append(button);
      if (item.kind === "submenu" && at.subOpen && at.item === index)
        li.append(list(item.items, true));
      ul.append(li);
    });
    return ul;
  }

  function currentItems(menus) {
    const top = menus[at.top]?.items ?? [];
    return top;
  }

  function focusCurrent() {
    let selector = `[data-pos="${at.top}"]`;
    if (at.open && at.subOpen && at.sub >= 0) selector = `[data-pos="s${at.sub}"]`;
    else if (at.open && at.item >= 0) selector = `[data-pos="i${at.item}"]`;
    const element = root.querySelector(selector);
    if (element === search?.element) {
      search.focus();
      onHint?.(null);
      return;
    }
    element?.focus();
    reportHint(element);
  }

  function reportHint(element) {
    onHint?.(element?.dataset.hint ?? null);
  }

  function close(returnFocus = true) {
    cancelHover();
    search?.reset();
    at.open = false;
    at.item = -1;
    at.subOpen = false;
    at.sub = -1;
    wantFocus = returnFocus;
    if (!returnFocus && root.contains(document.activeElement)) document.activeElement.blur();
    render();
    if (!returnFocus) onHint?.(null);
  }

  function openMenu(index, { first = false, item = null } = {}) {
    cancelHover();
    // A fresh query each time the menu with the search field is opened.
    if (!(at.open && at.top === index)) search?.reset();
    at.top = index;
    at.open = true;
    at.subOpen = false;
    at.sub = -1;
    const items = currentItems(effective());
    at.item = first ? moveItem(items, -1, 1) : -1;
    // The Help menu opens with the cursor in its search field, whichever way it was opened.
    if (items[0]?.kind === "search") at.item = 0;
    if (item !== null) at.item = item;
    wantFocus = true;
    render();
  }

  /** Open the menu that holds the search field and put the cursor in it (the Help search key). */
  function openSearch() {
    if (!search) return false;
    const menus = effective();
    const top = menus.findIndex((menu) => menu.items.some((entry) => entry.kind === "search"));
    if (top < 0) return false;
    openMenu(top, { item: menus[top].items.findIndex((entry) => entry.kind === "search") });
    return true;
  }

  /** Alt+Enter in the search: open the command's own menu and highlight its item. */
  function reveal(id) {
    if (!findItem(effective(), id)) return false;
    search?.reset();
    at.open = true;
    render();
    // Drawing may have moved menus behind "…"; find the place again as drawn.
    const place = findItem(effective(), id);
    if (!place) return false;
    at.top = place.top;
    at.open = true;
    at.item = place.item;
    at.subOpen = place.sub >= 0;
    at.sub = place.sub;
    wantFocus = true;
    render();
    return true;
  }

  function activate() {
    const menus = effective();
    const items = currentItems(menus);
    const inSub = at.subOpen && at.sub >= 0;
    const item = inSub ? items[at.item]?.items[at.sub] : items[at.item];
    if (!item) return;
    if (item.kind === "search") return; // Enter in the field is the field's (command-search-ui.js)
    if (item.kind === "submenu") {
      at.subOpen = true;
      at.sub = moveItem(item.items, -1, 1);
      render();
      return;
    }
    if (!item.enabled) return; // greyed: it stays, it teaches, it does nothing
    close(false);
    run(item.id, item.arg); // `arg`: what the item carries (an Open Recent entry's path)
  }

  root.addEventListener("keydown", (event) => {
    // Typing in the search field is the field's: no arrows, Space or letters are the bar's.
    if (search?.element.contains(event.target)) return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const menus = effective();
    const key = event.key;
    const items = at.open ? currentItems(menus) : [];
    const sub = at.subOpen ? items[at.item]?.items : null;
    const take = () => {
      event.preventDefault();
      event.stopPropagation();
    };
    if (key === "ArrowRight" || key === "ArrowLeft") {
      const direction = key === "ArrowRight" ? 1 : -1;
      take();
      if (at.open && direction === 1 && !at.subOpen && items[at.item]?.kind === "submenu") {
        activate();
      } else if (at.open && direction === -1 && at.subOpen) {
        at.subOpen = false;
        at.sub = -1;
        render();
      } else {
        const next = moveMenu(menus.length, at.top, direction);
        if (at.open) openMenu(next, { first: true });
        else {
          at.top = next;
          wantFocus = true;
          render();
        }
      }
    } else if (key === "ArrowDown" || key === "ArrowUp") {
      take();
      const direction = key === "ArrowDown" ? 1 : -1;
      if (!at.open) openMenu(at.top, { first: direction > 0 });
      else if (sub) {
        at.sub = moveItem(sub, at.sub, direction);
        render();
      } else {
        at.item = moveItem(items, at.item, direction);
        render();
      }
    } else if (key === "Home" || key === "End") {
      if (!at.open) return;
      take();
      const list2 = sub ?? items;
      const target = moveItem(list2, -1, key === "Home" ? 1 : -1);
      if (sub) at.sub = target;
      else at.item = target;
      render();
    } else if (key === "Enter" || key === " ") {
      take();
      if (!at.open) openMenu(at.top, { first: true });
      else activate();
    } else if (key === "Escape") {
      take();
      if (at.subOpen) {
        at.subOpen = false;
        at.sub = -1;
        render();
      } else close(true);
    } else if (key === "Tab") {
      close(false);
    }
  });

  root.addEventListener("click", (event) => {
    const button = event.target.closest?.("button[data-pos]");
    if (!button) return;
    const pos = button.dataset.pos;
    if (/^\d+$/.test(pos)) {
      const index = Number(pos);
      if (at.open && at.top === index) close(false);
      else openMenu(index);
      return;
    }
    const index = Number(pos.slice(1));
    if (pos[0] === "i") {
      at.item = index;
      at.subOpen = false;
      at.sub = -1;
    } else at.sub = index;
    activate();
  });

  // Mouse hover, as on a Mac: with a menu open, another title opens at once; a submenu opens
  // when the pointer rests on its row and closes when it moves to another row. Touch and pen
  // skip this (click and keys are unchanged). The decisions live in menu-hover.js.
  root.addEventListener("pointerover", (event) => {
    const button = event.target.closest?.("button[data-pos]");
    if (!button) return;
    reportHint(button);
    if (!isHoverPointer(event.pointerType)) return;
    const pos = button.dataset.pos;
    if (/^\d+$/.test(pos)) {
      cancelHover();
      if (topHover({ open: at.open, top: at.top, target: Number(pos) }) === "open")
        openMenu(Number(pos));
      return;
    }
    if (!at.open) return;
    if (pos[0] === "s") {
      cancelHover(); // arrived in the submenu: nothing pending applies any more
      return;
    }
    const row = Number(pos.slice(1));
    const rowIsSubmenu = button.getAttribute("aria-haspopup") === "menu";
    const subRect = root.querySelector(".submenu")?.getBoundingClientRect();
    const here = { x: event.clientX, y: event.clientY };
    const decision = rowHover({
      subOpen: at.subOpen,
      openRow: at.item,
      row,
      rowIsSubmenu,
      towardSub: at.subOpen && movingToward(lastPointer, here, subRect),
    });
    cancelHover();
    if (decision.act === "cancel") return;
    const apply = () => {
      hoverTimer = null;
      if (!at.open) return;
      if (decision.act === "open-sub") {
        const items = currentItems(effective());
        if (items[row]?.kind !== "submenu") return;
        at.item = row;
        at.subOpen = true;
        at.sub = -1;
      } else {
        at.subOpen = false;
        at.sub = -1;
      }
      render();
    };
    if (decision.delay > 0) hoverTimer = setTimeout(apply, decision.delay);
    else apply();
  });
  root.addEventListener("pointermove", (event) => {
    if (isHoverPointer(event.pointerType)) lastPointer = { x: event.clientX, y: event.clientY };
  });
  root.addEventListener("pointerout", (event) => {
    if (!root.contains(event.relatedTarget))
      reportHint(root.contains(document.activeElement) ? document.activeElement : null);
  });
  root.addEventListener("focusin", (event) =>
    reportHint(event.target.closest?.("button[data-pos]")),
  );
  // Focus moved elsewhere (help opened from an item, say): the menu steps aside.
  root.addEventListener("focusout", (event) => {
    const to = event.relatedTarget;
    if (at.open && to && !root.contains(to)) close(false);
  });
  document.addEventListener("pointerdown", (event) => {
    if (at.open && !root.contains(event.target)) close(false);
  });
  window.addEventListener("blur", () => at.open && close(false));

  // Refit when the room changes: the window, or the chips beside the bar.
  if (typeof ResizeObserver !== "undefined") {
    let lastRoom = -1;
    const observer = new ResizeObserver(() => {
      const spacer = root.parentElement?.querySelector(".spacer");
      const room = root.offsetWidth + (spacer?.offsetWidth ?? 0);
      if (room === lastRoom) return;
      lastRoom = room;
      render();
    });
    observer.observe(root);
    const spacer = root.parentElement?.querySelector(".spacer");
    if (root.parentElement) observer.observe(root.parentElement);
    if (spacer) observer.observe(spacer);
  }

  search?.setHooks({
    // Esc in the field: back to the title, as Esc in any menu. Enter or Tab: the menu is done.
    close: ({ restoreFocus }) => close(restoreFocus),
    // An arrow key the field has no use for moves on in the bar.
    exit(key) {
      const menus = effective();
      const items = currentItems(menus);
      if (key === "ArrowDown" || key === "ArrowUp") {
        at.item = moveItem(items, at.item, key === "ArrowDown" ? 1 : -1);
        wantFocus = true;
        render();
      } else
        openMenu(moveMenu(menus.length, at.top, key === "ArrowRight" ? 1 : -1), { first: true });
    },
  });

  render();
  return {
    isOpen: () => at.open,
    /**
     * A command was run by a key chord: flash the title of the menu that holds it for a moment
     * (menu-flash.js), so the key teaches where the command is. A menu that sits in the "…"
     * flashes that. Nothing when the menu is open (you are looking at it) or motion is off.
     */
    flash(id, event) {
      if (at.open || document.documentElement.dataset.motion === "off") return;
      const top = flashTop(getMenus(), id, event);
      if (top === null) return;
      const titles = root.querySelectorAll(".menu-title");
      const title = top < shown ? titles[top] : root.querySelector(".menu-more");
      if (!title) return;
      title.classList.add("flash");
      setTimeout(() => title.classList.remove("flash"), FLASH_MS);
    },
    openSearch,
    reveal,
    /**
     * Redraw from live data (a modifier went down or up, a key was remapped, the state changed).
     * While the cursor is in the search field the menu stays as it is, so typing is never
     * interrupted; only the results are searched again.
     */
    refresh() {
      if (search?.isFocused()) search.refresh();
      else render();
    },
  };
}
