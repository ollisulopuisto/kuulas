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
    // Preserve state-specific tips owned by another view. Only generated command
    // tips are refreshed when the keymap or language changes.
    if (t && entry?.labelKey && (!node.dataset.tip || node.dataset.cmdTip === node.dataset.tip)) {
      const name = t(entry.labelKey);
      const hintKey = `cmd.${node.dataset.cmd}.hint`;
      const hint = t(hintKey);
      node.dataset.tip = [
        name,
        hint !== hintKey && hint !== name ? hint : "",
        ...combos.map((combo) => formatShortcut(combo, platform)),
      ]
        .filter(Boolean)
        .join(" · ");
      node.dataset.cmdTip = node.dataset.tip;
    }
    // One tooltip owner: a native title must not compete with the custom tip.
    // Keep its accessible name when the view did not provide one explicitly.
    const title = node.getAttribute?.("title");
    if (node.dataset.tip && title !== null && title !== undefined) {
      if (!node.hasAttribute?.("aria-label") && !node.hasAttribute?.("aria-labelledby"))
        node.setAttribute("aria-label", title);
      node.removeAttribute?.("title");
    }
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
