// A small context menu for the track and bus headers. The items come from
// context-menu-model.js (commands from the registry); this file only draws them and
// handles the pointer and the keys: arrows step, Enter or Space picks, Escape and a
// click outside close it. One menu at a time.
import { stepItem } from "./context-menu-model.js";
import { t } from "./i18n.js";

/**
 * Open the menu at viewport (x, y). `items` as from contextMenuItems; `onPick(id)` runs
 * after the menu has closed. Returns { close }.
 */
export function openContextMenu({ x, y, items, onPick, onClose = () => {} }) {
  const menu = document.createElement("div");
  menu.className = "menu-list context-menu";
  menu.setAttribute("role", "menu");
  menu.setAttribute("aria-label", t("ui.context_menu"));
  const buttons = items.map((item) => {
    if (item.separator) {
      const rule = document.createElement("div");
      rule.setAttribute("role", "separator");
      menu.append(rule);
      return null;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = "menu-item";
    button.setAttribute("role", "menuitem");
    button.textContent = t(item.labelKey);
    button.tabIndex = -1;
    if (!item.enabled) button.setAttribute("aria-disabled", "true");
    button.addEventListener("click", () => {
      if (!item.enabled) return;
      close();
      onPick(item.id);
    });
    menu.append(button);
    return button;
  });

  let active = -1;
  const focusAt = (index) => {
    if (index < 0) return;
    active = index;
    buttons[index]?.focus();
  };

  const onKey = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      event.stopPropagation();
      focusAt(stepItem(items, active, event.key === "ArrowDown" ? 1 : -1));
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      event.stopPropagation();
      focusAt(stepItem(items, -1, event.key === "Home" ? 1 : -1));
    } else if (event.key === "Tab") {
      close();
    }
  };
  const onOutside = (event) => {
    if (!menu.contains(event.target)) close();
  };
  let closed = false;
  function close() {
    if (closed) return;
    closed = true;
    document.removeEventListener("keydown", onKey, true);
    document.removeEventListener("pointerdown", onOutside, true);
    removeEventListener("blur", close);
    removeEventListener("resize", close);
    menu.remove();
    onClose();
  }

  document.body.append(menu);
  // Keep the menu on screen.
  const box = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(0, Math.min(x, innerWidth - box.width - 4))}px`;
  menu.style.top = `${Math.max(0, Math.min(y, innerHeight - box.height - 4))}px`;
  document.addEventListener("keydown", onKey, true);
  document.addEventListener("pointerdown", onOutside, true);
  addEventListener("blur", close);
  addEventListener("resize", close);
  focusAt(stepItem(items, -1, 1));
  return { close };
}
