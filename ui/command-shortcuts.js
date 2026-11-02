import { shortcutsFor } from "./help.js";
import { formatShortcut } from "./i18n.js";

/** Accessibility uses the same live entries as menus and help, on every keymap refresh. */
export function applyCommandShortcuts(document, entries, platform, { t } = {}) {
  for (const node of document.querySelectorAll("[data-cmd]")) {
    const entry = entries.find((e) => e.id === node.dataset.cmd);
    const combos = entry ? shortcutsFor(node.dataset.cmd, entries) : [];
    node.setAttribute(
      "aria-keyshortcuts",
      combos
        .map((combo) => combo.replace(/\bMod\b/, platform === "mac" ? "Meta" : "Control"))
        .join(" "),
    );
    if (
      t &&
      entry?.labelKey &&
      (!node.hasAttribute?.("aria-label") || node.dataset.cmdAriaLabel === "auto") &&
      !node.hasAttribute?.("aria-labelledby")
    ) {
      node.setAttribute("aria-label", t(entry.labelKey));
      node.dataset.cmdAriaLabel = "auto";
    }
  }
  for (const node of document.querySelectorAll("[data-shortcut-cmd]")) {
    const combo = shortcutsFor(node.dataset.shortcutCmd, entries)[0];
    node.textContent = combo ? formatShortcut(combo, platform) : "";
  }
}
