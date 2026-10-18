// The small panel after an import (GUI-DESIGN.md §23): what happened, the
// one-click alternatives (One after another instead, Undo), what went wrong
// per file, and the remembered choices for the next import. The model and the
// remembered choices are pure; the panel itself is a few DOM nodes.

import { MONO_CHOICES } from "./mono-ask.js";

export const PREFS_KEY = "kuulas.import";
/** What "as today" means: the order the files were given, names from the files. */
export const DEFAULT_PREFS = Object.freeze({ order: "given", trackNaming: "file", mono: "ask" });
export const ORDERS = ["given", "name", "time"];
export const NAMINGS = ["file", "person"];
/** A clean result goes away by itself; one with failures stays until closed. */
export const CLEAN_MS = 12_000;

const pick = (value, allowed, fallback) => (allowed.includes(value) ? value : fallback);

/** The remembered choices; a missing, damaged or blocked store gives the defaults. */
export function loadImportPrefs(storage = globalThis.localStorage) {
  let stored = {};
  try {
    stored = JSON.parse(storage.getItem(PREFS_KEY) ?? "{}") ?? {};
  } catch {
    // Blocked or damaged: the defaults apply.
  }
  return {
    order: pick(stored.order, ORDERS, DEFAULT_PREFS.order),
    trackNaming: pick(stored.trackNaming, NAMINGS, DEFAULT_PREFS.trackNaming),
    mono: pick(stored.mono, MONO_CHOICES, DEFAULT_PREFS.mono),
  };
}

export function saveImportPrefs(prefs, storage = globalThis.localStorage) {
  try {
    storage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // Not remembered; it still applies to this session.
  }
}

/**
 * What the panel says. `summary` is summariseImport's result; `options` the
 * placement that was sent ({ mode }). `monoAsk`: the new stereo speech tracks
 * ([{id, name}]) the user is asked about. status: ok | partial | failed.
 */
export function panelModel(summary, options, monoAsk = []) {
  const { imported, failures, warnings } = summary;
  let status = "ok";
  if (imported === 0) status = "failed";
  else if (failures.length > 0) status = "partial";
  let titleKey = "ui.import.done_none";
  if (imported === 1) titleKey = "ui.import.done_one";
  else if (imported > 1) {
    titleKey = options.mode === "sequential" ? "ui.import.done_sequence" : "ui.import.done_sync";
  }
  return {
    status,
    titleKey,
    titleParams: { count: imported },
    imported,
    failures,
    warnings,
    monoAsk,
    canUndo: imported > 0,
    canSequence: imported > 1 && options.mode !== "sequential",
  };
}

const LABELS = {
  order: {
    given: "ui.import.order_given",
    name: "ui.import.order_name",
    time: "ui.import.order_time",
  },
  naming: { file: "ui.import.naming_file", person: "ui.import.naming_person" },
  mono: {
    ask: "ui.import.mono_ask",
    mono: "ui.import.mono_always",
    stereo: "ui.import.mono_never",
  },
};

/**
 * `root` is an empty element. `actions.undo()`, `actions.sequence()`,
 * `actions.mono(tracks)` and `actions.keepStereo()` do the work; `t` translates. show() puts a result up and remembers the history head
 * it belongs to; sync(head) takes it down once anything else has changed the
 * project (Undo would then undo something else).
 */
export function createImportPanel({ root, t, actions, storage, schedule = setTimeout }) {
  const doc = root.ownerDocument;
  let prefs = loadImportPrefs(storage);
  let shown = null; // { model, head }
  let timer = null;

  const el = (tag, props = {}, ...children) => {
    const node = Object.assign(doc.createElement(tag), props);
    node.append(...children);
    return node;
  };
  const button = (key, onClick, className = "button") =>
    el("button", { type: "button", className, textContent: t(key), onclick: onClick });

  function choice(labelKey, kind, values, current, onChange) {
    const select = el("select", { className: "select" });
    for (const value of values) {
      select.append(
        el("option", { value, textContent: t(LABELS[kind][value]), selected: value === current }),
      );
    }
    select.addEventListener("change", () => onChange(select.value));
    return el(
      "label",
      { className: "import-choice" },
      el("span", { textContent: t(labelKey) }),
      select,
    );
  }

  function render() {
    root.replaceChildren();
    if (!shown) {
      root.hidden = true;
      return;
    }
    const { model } = shown;
    root.dataset.status = model.status;
    const title = el("h3", { textContent: t(model.titleKey, model.titleParams) });
    const close = button("ui.notice.dismiss", hide, "button ghost icon");
    close.textContent = "×";
    close.setAttribute("aria-label", t("ui.notice.dismiss"));
    root.append(el("div", { className: "import-head" }, title, close));
    if (model.monoAsk.length > 0) {
      const names = model.monoAsk.map((track) => track.name).join(", ");
      root.append(
        el("p", {
          className: "import-mono",
          textContent: t("ui.import.mono_question", { count: model.monoAsk.length, names }),
        }),
        el(
          "div",
          { className: "import-actions" },
          button("ui.import.mono_yes", () => answerMono(true)),
          button("ui.import.mono_no", () => answerMono(false), "button ghost"),
        ),
      );
    }
    const row = el("div", { className: "import-actions" });
    if (model.canSequence) row.append(button("ui.import.sequence", () => actions.sequence()));
    if (model.canUndo)
      row.append(button("ui.transport.undo", () => actions.undo(), "button ghost"));
    if (row.children.length > 0) root.append(row);
    if (model.failures.length > 0 || model.warnings.length > 0) {
      const list = el("ul");
      for (const failure of model.failures)
        list.append(el("li", { textContent: t("ui.import.failed_file", failure) }));
      for (const warning of model.warnings)
        list.append(el("li", { className: "warn", textContent: t("ui.import.warning", warning) }));
      root.append(list);
    }
    root.append(
      el(
        "div",
        { className: "import-options" },
        el("span", { className: "hint", textContent: t("ui.import.next") }),
        choice("ui.import.order", "order", ORDERS, prefs.order, (value) =>
          remember({ order: value }),
        ),
        choice("ui.import.naming", "naming", NAMINGS, prefs.trackNaming, (value) =>
          remember({ trackNaming: value }),
        ),
        choice("ui.import.mono", "mono", MONO_CHOICES, prefs.mono, (value) =>
          remember({ mono: value }),
        ),
      ),
    );
    root.hidden = false;
  }

  function answerMono(makeMono) {
    const tracks = shown.model.monoAsk;
    shown = { ...shown, model: { ...shown.model, monoAsk: [] } };
    if (makeMono) actions.mono(tracks);
    else actions.keepStereo();
    // Turning into mono edits the project, which takes the panel down via sync().
    render();
    restartTimer();
  }

  function remember(change) {
    prefs = { ...prefs, ...change };
    saveImportPrefs(prefs, storage);
    restartTimer(); // choosing something is reading the panel: keep it up
  }

  function restartTimer() {
    clearTimeout(timer);
    timer = null;
    if (
      shown &&
      shown.model.status === "ok" &&
      shown.model.warnings.length === 0 &&
      shown.model.monoAsk.length === 0
    )
      timer = schedule(hide, CLEAN_MS);
  }

  function hide() {
    clearTimeout(timer);
    shown = null;
    render();
  }

  render();
  return {
    prefs: () => prefs,
    show(model, head) {
      shown = { model, head };
      render();
      restartTimer();
    },
    sync(head) {
      if (shown && head !== shown.head) hide();
    },
    hide,
    refresh: render,
  };
}
