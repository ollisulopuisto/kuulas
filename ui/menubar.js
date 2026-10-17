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

import { moveItem, moveMenu } from "./menu-model.js";

export function createMenubar({ root, getMenus, run, onHint, t }) {
  // open: whether a menu is dropped down; top: which; item/sub: positions inside it.
  const at = { open: false, top: 0, item: -1, subOpen: false, sub: -1 };
  let wantFocus = false; // one-shot: focus the current item after the next render

  root.setAttribute("role", "menubar");
  root.setAttribute("aria-label", t("menu.bar"));

  function render() {
    const menus = getMenus();
    const focusAfter = wantFocus || root.contains(document.activeElement);
    wantFocus = false;
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
      cell.append(button);
      if (at.open && at.top === index) cell.append(list(menu.items, false));
      root.append(cell);
    });
    if (focusAfter) focusCurrent();
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
        if (item.alternate) button.dataset.alternate = "";
        button.title = item.tooltip;
        if (item.keys) {
          const kbd = document.createElement("kbd");
          kbd.textContent = item.keys;
          button.append(kbd);
        }
        button.dataset.hint = item.tooltip;
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
    element?.focus();
    reportHint(element);
  }

  function reportHint(element) {
    onHint?.(element?.dataset.hint ?? null);
  }

  function close(returnFocus = true) {
    at.open = false;
    at.item = -1;
    at.subOpen = false;
    at.sub = -1;
    wantFocus = returnFocus;
    if (!returnFocus && root.contains(document.activeElement)) document.activeElement.blur();
    render();
    if (!returnFocus) onHint?.(null);
  }

  function openMenu(index, { first = false } = {}) {
    at.top = index;
    at.open = true;
    at.subOpen = false;
    at.sub = -1;
    at.item = first ? moveItem(currentItems(getMenus()), -1, 1) : -1;
    wantFocus = true;
    render();
  }

  function activate() {
    const menus = getMenus();
    const items = currentItems(menus);
    const inSub = at.subOpen && at.sub >= 0;
    const item = inSub ? items[at.item]?.items[at.sub] : items[at.item];
    if (!item) return;
    if (item.kind === "submenu") {
      at.subOpen = true;
      at.sub = moveItem(item.items, -1, 1);
      render();
      return;
    }
    if (!item.enabled) return; // greyed: it stays, it teaches, it does nothing
    close(false);
    run(item.id);
  }

  root.addEventListener("keydown", (event) => {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const menus = getMenus();
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

  // Moving over a menu while one is open follows the pointer, as on every desktop.
  root.addEventListener("pointerover", (event) => {
    const button = event.target.closest?.("button[data-pos]");
    if (!button) return;
    reportHint(button);
    const pos = button.dataset.pos;
    if (/^\d+$/.test(pos) && at.open && at.top !== Number(pos)) openMenu(Number(pos));
  });
  root.addEventListener("pointerout", (event) => {
    if (!root.contains(event.relatedTarget))
      reportHint(root.contains(document.activeElement) ? document.activeElement : null);
  });
  root.addEventListener("focusin", (event) =>
    reportHint(event.target.closest?.("button[data-pos]")),
  );
  document.addEventListener("pointerdown", (event) => {
    if (at.open && !root.contains(event.target)) close(false);
  });
  window.addEventListener("blur", () => at.open && close(false));

  render();
  return {
    isOpen: () => at.open,
    /** Redraw from live data (a modifier went down or up, a key was remapped, the state changed). */
    refresh: render,
  };
}
