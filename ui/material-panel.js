// The Material tab (docs/design/MATERIAL.md): every recording of the project, how much the edit
// plays of it, and two ways to use it again: copy it to the clipboard, or place it on the
// timeline. The decisions are in material-model.js; this draws and reports clicks.
import { t } from "./i18n.js";
import { barShares, FILTERS, filterRows, lengthText, stateKey } from "./material-model.js";

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
 * `actions`: filter(name), text(value), copy(id), place(id). The state it reads: `material`
 * ({ status, rows } or null while loading), `materialFilter` and `materialText`.
 */
export function createMaterialPanel({ root, actions }) {
  let signature = "";

  const filters = (current) => {
    const group = el("div", { class: "mat-filters", role: "group" });
    for (const name of FILTERS) {
      const node = el("button", {
        type: "button",
        class: "button mat-filter",
        textContent: t(`ui.material.filter.${name}`),
        "aria-pressed": String(name === current),
        dataset: { id: name, action: "filter" },
      });
      node.addEventListener("click", () => actions.filter(name));
      group.append(node);
    }
    return group;
  };

  const bar = (row) => {
    const shares = barShares(row);
    const part = (kind) =>
      el("span", { class: `mat-part ${kind}`, style: `flex-grow: ${shares[kind]}` });
    return el(
      "span",
      { class: "mat-bar", role: "img", "aria-label": t(stateKey(row)) },
      part("used"),
      part("cut"),
      part("unused"),
    );
  };

  const button = (row, action, labelKey) => {
    const node = el("button", {
      type: "button",
      class: "button ghost",
      textContent: t(labelKey),
      disabled: row.missing,
      dataset: { id: row.id, action },
    });
    node.addEventListener("click", () => actions[action](row.id));
    return node;
  };

  const rowNode = (row) =>
    el(
      "li",
      { class: "mat-row", dataset: { id: row.id, state: row.missing ? "missing" : row.state } },
      el("span", { class: "mat-name", textContent: row.name }),
      el("span", {
        class: "mat-meta",
        textContent: `${lengthText(row.seconds)} · ${t(stateKey(row))}${row.recorded ? ` · ${t("ui.material.take")}` : ""}`,
      }),
      bar(row),
      el(
        "span",
        { class: "mat-actions" },
        button(row, "copy", "ui.material.copy"),
        button(row, "place", "ui.material.place"),
      ),
    );

  // The three parts are made once, so the search field keeps the focus while you type.
  const filtersBox = el("div", { class: "mat-top" });
  const search = el("input", { type: "search", class: "mat-search" });
  search.addEventListener("input", () => actions.text(search.value));
  const bodyBox = el("div", { class: "mat-body" });
  let built = false;

  return {
    update(state) {
      const filter = state.materialFilter ?? "all";
      const text = state.materialText ?? "";
      const rows = state.material?.rows ?? null;
      const key = JSON.stringify([filter, text, rows]);
      if (key === signature) return;
      signature = key;
      if (!built) {
        root.replaceChildren(filtersBox, search, bodyBox);
        built = true;
      }
      search.placeholder = t("ui.material.search");
      search.setAttribute("aria-label", t("ui.material.search"));
      if (search.value !== text) search.value = text;
      filtersBox.replaceChildren(filters(filter));
      const shown = rows === null ? [] : filterRows(rows, filter, text);
      let body;
      if (rows === null)
        body = el("p", { class: "mat-note", textContent: t("ui.material.loading") });
      else if (rows.length === 0)
        body = el("p", { class: "mat-note", textContent: t("ui.material.empty") });
      else if (shown.length === 0)
        body = el("p", { class: "mat-note", textContent: t("ui.material.no_match") });
      else body = el("ul", { class: "mat-list" }, ...shown.map(rowNode));
      bodyBox.replaceChildren(body);
    },
  };
}
