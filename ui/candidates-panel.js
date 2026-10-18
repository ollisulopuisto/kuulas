// The Candidates tab (WP18): the cut candidates by time, with the summary chips, a
// "Find candidates" button, the filter "Open only" and the action bar (Preview, Delete,
// Cut and close gap, Keep) with the preview bar under the list. The panel only draws and
// reports; what a click does is app.js's (actions), the order and the numbers are
// candidates-model.js's. Spec: GUI-DESIGN.md, 3.6 and the 'candidates' screen.
import { kindFacts, listedRows, previewBar } from "./candidates-model.js";
import { formatDuration, formatNumber, getLanguage, t } from "./i18n.js";

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

const seconds = (value) => formatNumber(value, { digits: 1 });

/**
 * `actions`: select(row), find(), toggleOpenOnly(), apply(id, mode), keep(id), preview(row),
 * can(commandId, state) -> boolean (the registry's `can`, so the buttons and the keys agree).
 */
export function createCandidatesPanel({ root, getState, actions }) {
  let signature = "";

  const title = el("h2");
  const find = el("button", { type: "button", class: "button", id: "cand-find" });
  const filter = el("input", { type: "checkbox", id: "cand-open-only" });
  const filterLabel = el("label", { class: "cand-filter", htmlFor: "cand-open-only" }, filter);
  const filterText = el("span");
  filterLabel.append(filterText);
  const chips = el("div", { class: "cand-summary", role: "status" });
  const status = el("p", { class: "hint", hidden: true });
  const list = el("ul", { class: "cands", role: "listbox" });
  const scroller = el("div", { class: "cand-scroll" }, list);
  const bar = el("div", { class: "preview-bar", hidden: true, role: "img" });
  const preview = el("button", { type: "button", class: "button", id: "cand-preview" });
  const del = el("button", { type: "button", class: "button primary", id: "cand-delete" });
  const cut = el("button", { type: "button", class: "button", id: "cand-cut" });
  const keep = el("button", { type: "button", class: "button", id: "cand-keep" });
  const actionbar = el("div", { class: "actionbar" }, bar, preview, del, cut, keep);
  root.replaceChildren(
    title,
    el("div", { class: "cand-tools" }, find, filterLabel),
    chips,
    status,
    scroller,
    actionbar,
  );

  const rowOf = (id) => list.querySelector(`[data-id="${CSS.escape(id)}"]`);

  function candidateRow(row, current) {
    const kind = kindFacts(row.kind);
    const classes = ["cand", row.state];
    if (current) classes.push("current");
    const where =
      row.start === null
        ? t("ui.candidates.off_timeline")
        : formatDuration(row.start / getState().project.rate);
    const quote = row.text ? `“${row.text}”` : row.reason;
    const node = el(
      "li",
      {
        class: classes.join(" "),
        role: "option",
        id: `cand-${row.id}`,
        tabIndex: current ? 0 : -1,
        "aria-selected": String(current),
        dataset: { id: row.id },
      },
      el("span", { class: "when", textContent: where }),
      el("span", {
        class: "dur",
        textContent: t("ui.candidates.seconds", { seconds: seconds(row.seconds) }),
      }),
      el("span", {
        class: `state ${row.state}`,
        textContent: t(`ui.candidates.state.${row.state}`),
      }),
      el(
        "span",
        { class: "kind" },
        el("span", { class: "kind-icon", "aria-hidden": "true", textContent: kind.icon }),
        t(kind.key),
      ),
      el("span", { class: "quote", textContent: quote, title: quote }),
    );
    node.addEventListener("click", () => {
      actions.select(row);
      node.focus({ preventScroll: true });
    });
    return node;
  }

  function draw(state) {
    const rows = state.candidates ?? [];
    const shown = listedRows(rows, state.candidatesOpenOnly !== false);
    const current = rows.find((row) => row.id === state.candidateCurrent) ?? null;
    const previewData =
      state.candidatePreview && state.candidatePreview.id === current?.id
        ? state.candidatePreview
        : null;
    const next = JSON.stringify([
      getLanguage(),
      shown,
      state.candidateSummary,
      state.candidateCurrent,
      state.candidatesOpenOnly,
      state.candidateBusy,
      state.candidateFound,
      previewData,
      state.project?.rate,
      state.panel === "candidates",
    ]);
    if (next === signature) return;
    signature = next;

    title.textContent = t("ui.candidates.title");
    find.textContent = t(state.candidateBusy ? "ui.candidates.finding" : "ui.candidates.find");
    find.disabled = !actions.can("candidate.find", state);
    filter.checked = state.candidatesOpenOnly !== false;
    filterText.textContent = t("ui.candidates.filter_open");
    const summary = state.candidateSummary ?? { open: 0, cut: 0, kept: 0 };
    chips.replaceChildren(
      ...["open", "cut", "kept"].map((name) =>
        el("span", {
          class: `chip ${name}`,
          textContent: t(`ui.candidates.chip.${name}`, { count: summary[name] ?? 0 }),
        }),
      ),
    );
    const found = state.candidateFound;
    if (found && found.added === 0 && found.dropped === 0) {
      status.textContent = t("ui.candidates.nothing");
    } else if (found && (found.added > 0 || found.dropped > 0)) {
      status.textContent = t("ui.candidates.found", found);
    } else if (shown.length === 0) {
      status.textContent = t(
        rows.length === 0 ? "ui.candidates.empty" : "ui.candidates.empty_open",
      );
    } else {
      status.textContent = "";
    }
    status.hidden = status.textContent === "";
    list.setAttribute("aria-label", t("ui.candidates.list_label"));
    list.replaceChildren(
      ...shown.map((row) => candidateRow(row, row.id === state.candidateCurrent)),
    );

    const rate = state.project?.rate ?? 1;
    const lengths = previewData ? previewBar(previewData, rate) : null;
    bar.hidden = lengths === null;
    if (lengths) {
      const part = (cls, key, value) =>
        el("span", { class: cls, textContent: t(key, { seconds: seconds(value) }) });
      bar.setAttribute("aria-label", t("ui.candidates.preview_label"));
      // Proportional widths; whole numbers, because fr values that add up to less than 1
      // would not fill the bar.
      const fr = (value) => Math.max(1, Math.round(value * 100));
      bar.style.gridTemplateColumns = `${fr(lengths.before)}fr ${fr(lengths.skipped)}fr ${fr(lengths.after)}fr`;
      bar.replaceChildren(
        part("", "ui.candidates.preview_before", lengths.before),
        part("skip", "ui.candidates.preview_skip", lengths.skipped),
        part("", "ui.candidates.preview_after", lengths.after),
      );
    }
    preview.textContent = t("ui.candidates.preview");
    del.textContent = t("ui.candidates.delete");
    cut.textContent = t("ui.candidates.cut_close");
    keep.textContent = t("ui.candidates.keep");
    preview.disabled = !actions.can("candidate.preview", state);
    del.disabled = !actions.can("candidate.apply", state);
    cut.disabled = !actions.can("candidate.apply_ripple", state);
    keep.disabled = !actions.can("candidate.reject", state);
    const currentNode = state.candidateCurrent ? rowOf(state.candidateCurrent) : null;
    currentNode?.scrollIntoView({ block: "nearest" });
  }

  find.addEventListener("click", () => actions.find());
  filter.addEventListener("change", () => actions.toggleOpenOnly());
  preview.addEventListener("click", () => actions.run("candidate.preview"));
  del.addEventListener("click", () => actions.run("candidate.apply"));
  cut.addEventListener("click", () => actions.run("candidate.apply_ripple"));
  keep.addEventListener("click", () => actions.run("candidate.reject"));

  root.addEventListener("keydown", (event) => {
    const direction = { ArrowDown: 1, ArrowUp: -1 }[event.key];
    if (!direction || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (event.target.closest?.(".actionbar, .cand-tools")) return;
    event.preventDefault();
    const state = getState();
    const shown = listedRows(state.candidates ?? [], state.candidatesOpenOnly !== false);
    const at = shown.findIndex((row) => row.id === state.candidateCurrent);
    const target = shown[Math.min(shown.length - 1, Math.max(0, at + direction))];
    if (!target) return;
    actions.select(target);
    queueMicrotask(() => rowOf(target.id)?.focus());
  });
  // The panel itself takes the keyboard (focus cycling): hand it to the current row.
  root.addEventListener("focus", (event) => {
    if (event.target !== root) return;
    const id = getState().candidateCurrent;
    (id && rowOf(id))?.focus();
  });

  return { update: draw };
}
