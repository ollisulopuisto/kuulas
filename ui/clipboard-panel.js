// The Clipboard tab (WP46): the history of copies and cuts, newest first. Each entry has
// its name, how long it is, pin, rename, delete and "Paste again"; two choices say how a
// paste lands (insert or overwrite, on the same tracks or the current one). The panel only
// draws and reports; what a click does is app.js's (actions), what a paste does is
// edit-plans.js's.
import {
  entryDetails,
  entryTitle,
  filterEntries,
  PASTE_MODES,
  PASTE_TARGETS,
  pasteChoice,
  shortDuration,
} from "./clipboard.js";
import { getLanguage, t } from "./i18n.js";

const el = (tag, props = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "class") node.className = value;
    else if (key in node) node[key] = value;
    else node.setAttribute(key, value);
  }
  node.append(...children);
  return node;
};

/**
 * `actions`: select(id), preview(id), filter(text), pin(id, pinned), rename(id, name), remove(id), pasteAgain(id),
 * choose({ pasteMode } | { pasteTarget }), canPasteAgain(state) -> boolean.
 */
export function createClipboardPanel({ root, actions }) {
  let signature = "";
  let editing = null; // the id being renamed

  const select = (name, values, current, onChange) => {
    const node = el("select", { class: "button", id: `clip-${name}`, dataset: { choice: name } });
    for (const value of values) {
      node.append(el("option", { value, textContent: t(`ui.clipboard.${name}.${value}`) }));
    }
    node.value = current;
    node.addEventListener("change", () => onChange(node.value));
    return node;
  };

  function entryRow(entry, state, rate, canPaste) {
    const selected = (state.clipboardSelected ?? state.clipboard[0]?.id) === entry.id;
    const meta = [
      t("ui.clipboard.meta", { count: entry.clips, duration: shortDuration(entry.length / rate) }),
    ];
    if (entry.missing_here > 0) {
      meta.push(t("ui.clipboard.missing_here", { count: entry.missing_here }));
    }
    const title = entryTitle(entry, rate, t);
    let name;
    if (editing === entry.id) {
      name = el("input", {
        type: "text",
        class: "clip-rename",
        value: entry.name?.trim() ? entry.name : "",
        placeholder: title,
        "aria-label": t("ui.clipboard.rename_label"),
        dataset: { id: entry.id, action: "rename-input" },
      });
      name.addEventListener("keydown", (event) => {
        event.stopPropagation();
        if (event.key === "Enter") {
          editing = null;
          actions.rename(entry.id, name.value);
        } else if (event.key === "Escape") {
          editing = null;
          signature = "";
          update(state);
        }
      });
      name.addEventListener("blur", () => {
        if (editing !== entry.id) return;
        editing = null;
        actions.rename(entry.id, name.value);
      });
    } else {
      name = el(
        "button",
        {
          type: "button",
          class: "clip-main",
          "aria-pressed": String(selected),
          dataset: { id: entry.id, action: "select" },
        },
        el("span", { class: "clip-name", textContent: title }),
        el("span", { class: "clip-meta", textContent: meta.join(" · ") }),
        el("span", { class: "clip-meta", textContent: entryDetails(entry, rate, t) }),
      );
      name.addEventListener("click", () => actions.select(entry.id));
    }
    const button = (action, label, onClick, extra = {}) => {
      const node = el("button", {
        type: "button",
        class: "button ghost",
        textContent: label,
        dataset: { id: entry.id, action },
        ...extra,
      });
      node.addEventListener("click", onClick);
      return node;
    };
    const buttons = el(
      "span",
      { class: "clip-actions" },
      button("preview", t("ui.clipboard.preview"), () => actions.preview(entry.id)),
      button("paste", t("ui.clipboard.paste_again"), () => actions.pasteAgain(entry.id), {
        disabled: !canPaste,
      }),
      button(
        "pin",
        t(entry.pinned ? "ui.clipboard.unpin" : "ui.clipboard.pin"),
        () => actions.pin(entry.id, !entry.pinned),
        { "aria-pressed": String(entry.pinned) },
      ),
      button("rename", t("ui.clipboard.rename"), () => {
        editing = entry.id;
        signature = "";
        update(state);
        root.querySelector(".clip-rename")?.focus();
      }),
      button("delete", t("ui.clipboard.delete"), () => actions.remove(entry.id)),
    );
    return el(
      "li",
      { class: "clip-entry", dataset: { id: entry.id, selected: String(selected) } },
      name,
      buttons,
    );
  }

  function update(state) {
    const list = state.clipboard ?? [];
    const choice = pasteChoice(state);
    const rate = state.project?.rate ?? 48000;
    // Whether "Paste again" can run depends on the cursor, the track and the project; the
    // answer, not the cursor, goes in the signature, so playback does not redraw the list.
    const canPaste = list.length > 0 && actions.canPasteAgain(state);
    const next = JSON.stringify([
      getLanguage(),
      list,
      rate,
      choice,
      state.clipboardSelected,
      editing,
      canPaste,
      state.clipboardFilter ?? "",
    ]);
    if (next === signature) return;
    signature = next;
    const active = document.activeElement;
    const keep =
      root.contains(active) && active.dataset?.id
        ? {
            id: active.dataset.id,
            action: active.dataset.action,
            caret: [active.selectionStart, active.selectionEnd],
          }
        : null;
    const query = state.clipboardFilter ?? "";
    const shown = filterEntries(list, query, rate, t);
    root.replaceChildren(
      el("h2", { textContent: t("ui.clipboard.title") }),
      el(
        "div",
        { class: "clip-choice" },
        el(
          "label",
          {},
          el("span", { textContent: t("ui.clipboard.mode") }),
          select("mode", PASTE_MODES, choice.mode, (value) => actions.choose({ pasteMode: value })),
        ),
        el(
          "label",
          {},
          el("span", { textContent: t("ui.clipboard.target") }),
          select("target", PASTE_TARGETS, choice.target, (value) =>
            actions.choose({ pasteTarget: value }),
          ),
        ),
      ),
    );
    if (list.length === 0) {
      root.append(el("p", { class: "hint", textContent: t("ui.clipboard.empty") }));
    } else {
      const filter = el("input", {
        type: "search",
        class: "clip-filter",
        value: query,
        placeholder: t("ui.clipboard.filter_placeholder"),
        "aria-label": t("ui.clipboard.filter_label"),
        dataset: { id: "filter", action: "filter" },
      });
      filter.addEventListener("input", () => actions.filter(filter.value));
      filter.addEventListener("keydown", (event) => {
        event.stopPropagation(); // typing a name is not a shortcut
        if (event.key === "Escape" && filter.value) {
          event.preventDefault();
          actions.filter("");
        }
      });
      root.append(filter);
      root.append(
        shown.length === 0
          ? el("p", { class: "hint", textContent: t("ui.clipboard.no_matches") })
          : el(
              "ul",
              { class: "clip-list", "aria-label": t("ui.clipboard.list_label") },
              ...shown.map((entry) => entryRow(entry, state, rate, canPaste)),
            ),
      );
    }
    if (keep) {
      const again = root.querySelector(
        `[data-id="${CSS.escape(keep.id)}"][data-action="${keep.action}"]`,
      );
      again?.focus();
      if (keep.caret?.[0] != null) again?.setSelectionRange?.(...keep.caret);
    }
  }

  return { update };
}
