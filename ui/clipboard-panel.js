// The Clipboard tab (WP46, WP65): four views behind a segmented control. *This project* is
// the project's own clipboard, newest first, with each entry's name, metadata line, Share star,
// Series toggle (in a series), play, "Paste again", rename and delete. *Series* is the series
// shelf, the series music (docs/design/CLIPBOARD-SHELVES.md). *Shared* lists the entries marked
// as worth sharing, from every project. *Other projects* lists the recent projects (click one to read its
// clipboard, read-only) and a button that picks any project. Entries that are not this
// project's own have "Paste here" and "Copy to this project", both of which adopt the entry
// first. Two choices say how a paste lands (insert or overwrite, on the same tracks or the
// current one). The panel only draws and reports; what a click does is app.js's (actions),
// what a paste does is edit-plans.js's.
import {
  CLIPBOARD_VIEWS,
  clipboardView,
  entryMeta,
  entryTitle,
  filterEntries,
  filterEscapeAction,
  foreignState,
  keepCount,
  levelHint,
  PASTE_MODES,
  PASTE_TARGETS,
  pasteChoice,
  projectLabel,
} from "./clipboard.js";
import { CLIP_DRAG_TYPE } from "./clipboard-drag.js";
import { reorderTarget } from "./clipboard-order.js";
import { previewButton } from "./clipboard-preview.js";
import { formatAbsoluteTime, getLanguage, t } from "./i18n.js";

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
 * `actions`: select(id), preview(id), stopPreview(id), filter(text), rename(id, name), remove(id), pasteAgain(id),
 * share(id, on), view(name), choose({ pasteMode } | { pasteTarget }), keep(n), clearOld(),
 * toggleProject(path), openProject(), openPath(path), hasPicker() -> boolean,
 * adopt(entry, from[, shelf]), pasteHere(entry, from[, shelf]), now() -> UTC epoch seconds,
 * canPasteAgain(state) -> boolean, seriesShelf(id, on), seriesRemove(id), seriesPlace(),
 * openSeries(), dragStart(entry, { shelf, from }), dragEnd(). `shelf` is "series" for an entry
 * of the series shelf; a drag's shelf is "project", "series", "shared" or "other".
 */
export function createClipboardPanel({ root, actions }) {
  let signature = "";
  let meter = null; // the playing chip's progress meter (filled every frame by progress())
  let editing = null; // the id being renamed
  let pathDraft = ""; // the typed path of a project (a browser has no folder picker)

  const select = (name, values, current, onChange) => {
    const node = el("select", { class: "button", id: `clip-${name}`, dataset: { choice: name } });
    for (const value of values) {
      node.append(el("option", { value, textContent: t(`ui.clipboard.${name}.${value}`) }));
    }
    node.value = current;
    node.addEventListener("change", () => onChange(node.value));
    return node;
  };

  const button = (id, action, label, onClick, extra = {}) => {
    const node = el("button", {
      type: "button",
      class: "button ghost",
      textContent: label,
      dataset: { id, action },
      ...extra,
    });
    node.addEventListener("click", onClick);
    return node;
  };

  /** A chip's action: a square block button, the icon over the label (the app's block style). */
  const block = (id, action, label, icon, onClick, extra = {}) =>
    button(id, action, label, onClick, { class: "button block", "data-icon": icon, ...extra });

  /** The name and the metadata lines, shared by every kind of row. */
  const labels = (entry, rate) => {
    const counts = [t("ui.clipboard.clip_count", { count: entry.clips })];
    if (entry.missing_here > 0) {
      counts.push(t("ui.clipboard.missing_here", { count: entry.missing_here }));
    }
    return [
      el("span", { class: "clip-name", textContent: entryTitle(entry, rate, t) }),
      el("span", {
        class: "clip-meta",
        textContent: entryMeta(entry, rate, actions.now(), t),
      }),
      el("span", { class: "clip-meta", textContent: counts.join(" · ") }),
    ];
  };

  function ownRow(entry, state, rate, canPaste) {
    const selected = (state.clipboardSelected ?? state.clipboard[0]?.id) === entry.id;
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
        ...labels(entry, rate),
      );
      name.addEventListener("click", () => actions.select(entry.id));
    }
    // The cart number: Alt+n plays this entry when it holds n (cart-model.js); a click picks it.
    const cart = el("button", {
      type: "button",
      class: "button block clip-cart",
      textContent: entry.cart ? String(entry.cart) : "–",
      title: t("ui.clipboard.cart_title"),
      "aria-label": t("ui.clipboard.cart"),
      dataset: { id: entry.id, action: "cart" },
    });
    cart.addEventListener("click", (event) => actions.pickCart(entry.id, event));
    // The star: marked entries are listed under Shared by every project.
    const star = el("button", {
      type: "button",
      class: "button block clip-star",
      textContent: entry.shared ? "★" : "☆",
      title: t(entry.shared ? "ui.clipboard.share_on" : "ui.clipboard.share_off"),
      "aria-label": t("ui.clipboard.share"),
      "aria-pressed": String(Boolean(entry.shared)),
      dataset: { id: entry.id, action: "share" },
    });
    star.addEventListener("click", () => actions.share(entry.id, !entry.shared));
    // The Series toggle, only in a series: pressed when the entry is on the series shelf.
    const series = state.clipboardSeries;
    const extra = [];
    if (series?.link) {
      const on = (series.entries ?? []).some((item) => item.id === entry.id);
      extra.push(
        block(
          entry.id,
          "series-shelf",
          t("ui.clipboard.series_toggle"),
          "layers",
          () => actions.seriesShelf(entry.id, !on),
          {
            "aria-pressed": String(on),
            title: t(on ? "ui.clipboard.series_on" : "ui.clipboard.series_off"),
          },
        ),
      );
    }
    // Play, or Stop while this entry's preview plays (only the playing chip shows Stop).
    const play = previewButton(state.clipboardPlaying, entry.id);
    const buttons = el(
      "span",
      { class: "clip-actions" },
      cart,
      star,
      ...extra,
      block(
        entry.id,
        "preview",
        t(play.labelKey),
        play.icon,
        () => (play.playing ? actions.stopPreview(entry.id) : actions.preview(entry.id)),
        { "aria-pressed": String(play.playing), "aria-label": t(play.labelKey) },
      ),
      block(
        entry.id,
        "paste",
        t("ui.clipboard.paste_again"),
        "paste",
        () => actions.pasteAgain(entry.id),
        { disabled: !canPaste },
      ),
      block(entry.id, "rename", t("ui.clipboard.rename"), "rename", () => {
        editing = entry.id;
        signature = "";
        update(state);
        root.querySelector(".clip-rename")?.focus();
      }),
      block(entry.id, "delete", t("ui.clipboard.delete"), "trash", () => actions.remove(entry.id)),
    );
    const hint = levelHint(state.clipboardLevel, entry.id, t);
    // While it plays, the chip's bottom edge fills left to right with the preview (progress()).
    const progressBar = play.playing ? [progressMeter(entry.id)] : [];
    const row = el(
      "li",
      {
        class: "clip-entry",
        dataset: { id: entry.id, selected: String(selected), playing: String(play.playing) },
      },
      name,
      ...(hint
        ? [el("span", { class: "clip-meta clip-level", role: "status", textContent: hint })]
        : []),
      buttons,
      ...progressBar,
    );
    reorderable(row, entry, state);
    row.addEventListener("contextmenu", (event) => actions.contextMenu?.(entry.id, event));
    return draggable(row, entry, { shelf: "project", from: "" }, "copyMove");
  }

  /**
   * Dropping another entry of this list on a row puts it before or after that row (the list is
   * the order shown and the order Paste reads; clipboard-order.js). Off while the list is
   * filtered: the rows shown are not the whole list.
   */
  function reorderable(row, entry, state) {
    if ((state.clipboardFilter ?? "").trim() !== "") return;
    const ids = state.clipboard.map((item) => item.id);
    const mark = (value) => {
      if (value) row.dataset.drop = value;
      else delete row.dataset.drop;
    };
    const target = (event) => {
      const box = row.getBoundingClientRect();
      return reorderTarget({
        draggedId: dragged,
        rowId: entry.id,
        offsetY: event.clientY - box.top,
        rowHeight: box.height,
        ids,
      });
    };
    row.addEventListener("dragover", (event) => {
      if (![...(event.dataTransfer?.types ?? [])].includes(CLIP_DRAG_TYPE) || !dragged) return;
      const where = target(event);
      if (!where) return mark("");
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
      const box = row.getBoundingClientRect();
      mark(event.clientY - box.top < box.height / 2 ? "before" : "after");
    });
    row.addEventListener("dragleave", () => mark(""));
    row.addEventListener("drop", (event) => {
      mark("");
      const where = dragged ? target(event) : null;
      if (!where) return;
      event.preventDefault();
      actions.move(dragged, where.before);
    });
  }

  function progressMeter(id) {
    const fill = el("span", { class: "clip-progress-fill" });
    fill.style.transform = "scaleX(0)";
    meter = el(
      "span",
      {
        class: "clip-progress",
        role: "progressbar",
        "aria-label": t("ui.clipboard.preview_progress"),
        "aria-valuemin": "0",
        "aria-valuemax": "100",
        "aria-valuenow": "0",
        dataset: { id, action: "preview-progress" },
      },
      fill,
    );
    return meter;
  }

  /** The playing chip's meter at `fraction` (0..1) of the preview; nothing when none plays. */
  function progress(fraction) {
    if (!meter) return;
    const f = Math.min(1, Math.max(0, Number(fraction) || 0));
    meter.children[0].style.transform = `scaleX(${f})`;
    meter.setAttribute("aria-valuenow", String(Math.round(f * 100)));
  }

  /**
   * An entry that is not this project's own (shared, or read from another project): read-only,
   * so no play button (it plays once it is copied here), but it can be adopted. `from` is the
   * folder of the project it was read from ("" for the shared list); `scope` keeps ids unique.
   */
  function foreignRow(entry, state, rate, { from, scope, unshare, shelf }) {
    const id = `${scope}:${entry.id}`;
    const canPaste = Boolean(state.project);
    // The series shelf's entries are adopted through the series (its recordings' paths).
    const via = shelf ? [shelf] : [];
    const buttons = el(
      "span",
      { class: "clip-actions" },
      block(
        id,
        "paste-here",
        t("ui.clipboard.paste_here"),
        "paste",
        () => actions.pasteHere(entry, from, ...via),
        { disabled: !canPaste },
      ),
      block(
        id,
        "copy-here",
        t("ui.clipboard.copy_here"),
        "copy",
        () => actions.adopt(entry, from, ...via),
        { disabled: !canPaste },
      ),
    );
    if (shelf === "series") {
      buttons.append(
        block(id, "series-remove", t("ui.clipboard.series_remove"), "close", () =>
          actions.seriesRemove(entry.id),
        ),
      );
    }
    if (unshare) {
      buttons.append(
        block(id, "unshare", t("ui.clipboard.unshare"), "close", () =>
          actions.share(entry.id, false),
        ),
      );
    }
    const row = el(
      "li",
      { class: "clip-entry", dataset: { id, foreign: "true" } },
      el("span", { class: "clip-main" }, ...labels(entry, rate)),
      buttons,
    );
    return draggable(row, entry, { shelf: shelf ?? (from ? "other" : "shared"), from });
  }

  /**
   * A row dragged onto the timeline pastes its entry there (clipboard-drag.js). The drag carries
   * the entry id; which entry and shelf it is goes to the app, as a drag's data cannot be read
   * before the drop.
   */
  function draggable(row, entry, source, allowed = "copy") {
    row.setAttribute("draggable", "true");
    row.addEventListener("dragstart", (event) => {
      event.dataTransfer?.setData(CLIP_DRAG_TYPE, entry.id);
      if (event.dataTransfer) event.dataTransfer.effectAllowed = allowed;
      dragged = source.shelf === "project" ? entry.id : null;
      actions.dragStart(entry, source);
    });
    row.addEventListener("dragend", () => {
      dragged = null;
      actions.dragEnd();
    });
    return row;
  }
  // The entry of THIS list being dragged (the data of a drag cannot be read before the drop).
  let dragged = null;

  const list = (label, rows) => el("ul", { class: "clip-list", "aria-label": label }, ...rows);

  function viewSwitch(current) {
    const group = el("div", {
      class: "clip-views",
      role: "group",
      "aria-label": t("ui.clipboard.view_label"),
    });
    for (const name of CLIPBOARD_VIEWS) {
      const node = el("button", {
        type: "button",
        class: "button clip-view",
        textContent: t(`ui.clipboard.view.${name}`),
        "aria-pressed": String(name === current),
        dataset: { id: `view-${name}`, action: "view" },
      });
      node.addEventListener("click", () => actions.view(name));
      group.append(node);
    }
    return group;
  }

  function filterBox(query) {
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
      const onEsc = filterEscapeAction(event.key, filter.value);
      // Esc on an empty field is the escape order's (blur, then the timeline); the rest is typing,
      // which is not a shortcut.
      if (onEsc !== "pass") event.stopPropagation();
      if (onEsc === "clear") {
        event.preventDefault();
        actions.filter("");
      }
    });
    return filter;
  }

  // "Clear old entries" (WP65): the one way entries leave besides deleting one by hand.
  function clearRow(state) {
    const field = el("input", {
      type: "number",
      class: "clip-keep",
      min: "1",
      step: "1",
      value: String(keepCount(state)),
      "aria-label": t("ui.clipboard.keep_label"),
      dataset: { id: "keep", action: "keep" },
    });
    field.addEventListener("change", () => actions.keep(field.value));
    field.addEventListener("keydown", (event) => event.stopPropagation());
    const clear = button("clear-old", "clear-old", t("ui.clipboard.clear_old"), () =>
      actions.clearOld(),
    );
    clear.className = "button block";
    clear.dataset.icon = "trash";
    return el(
      "div",
      { class: "actionbar clip-clear", role: "group", "aria-label": t("ui.clipboard.title") },
      clear,
      el(
        "label",
        { class: "clip-keep-field form-inline" },
        el("span", { textContent: t("ui.clipboard.keep_label") }),
        field,
      ),
    );
  }

  const hint = (key) => el("p", { class: "hint", textContent: t(key) });

  function projectView(state, rate, canPaste, query) {
    const own = state.clipboard ?? [];
    if (own.length === 0) return [hint("ui.clipboard.empty")];
    const shown = filterEntries(own, query, rate, t);
    return [
      filterBox(query),
      shown.length === 0
        ? hint("ui.clipboard.no_matches")
        : list(
            t("ui.clipboard.list_label"),
            shown.map((entry) => ownRow(entry, state, rate, canPaste)),
          ),
    ];
  }

  function sharedView(state, rate, query) {
    const shared = state.clipboardShared ?? [];
    if (shared.length === 0) return [hint("ui.clipboard.shared_empty")];
    const shown = filterEntries(shared, query, rate, t);
    return [
      hint("ui.clipboard.foreign_hint"),
      filterBox(query),
      shown.length === 0
        ? hint("ui.clipboard.no_matches")
        : list(
            t("ui.clipboard.shared_list_label"),
            shown.map((entry) =>
              foreignRow(entry, state, rate, { from: "", scope: "shared", unshare: true }),
            ),
          ),
    ];
  }

  function seriesView(state, rate, query) {
    const shelf = state.clipboardSeries ?? { link: null, found: false, entries: [] };
    if (!shelf.link) {
      const open = button("open-series", "open-series", t("cmd.series.dialog"), () =>
        actions.openSeries(),
      );
      return [hint("ui.clipboard.series_none"), el("div", { class: "clip-open" }, open)];
    }
    const name = el("p", {
      class: "hint",
      textContent: t("ui.clipboard.series_name", { name: shelf.link.name }),
    });
    if (!shelf.found) return [name, hint("ui.clipboard.series_missing")];
    const entries = shelf.entries ?? [];
    if (entries.length === 0) return [name, hint("ui.clipboard.series_empty")];
    const place = block(
      "series-place",
      "series-place",
      t("ui.clipboard.series_place"),
      "import",
      () => actions.seriesPlace(),
      { disabled: !state.project },
    );
    const shown = filterEntries(entries, query, rate, t);
    return [
      name,
      el(
        "div",
        { class: "actionbar", role: "group", "aria-label": t("ui.clipboard.view.series") },
        place,
      ),
      filterBox(query),
      shown.length === 0
        ? hint("ui.clipboard.no_matches")
        : list(
            t("ui.clipboard.series_list_label"),
            shown.map((entry) =>
              foreignRow(entry, state, rate, {
                from: "",
                scope: "series",
                unshare: false,
                shelf: "series",
              }),
            ),
          ),
    ];
  }

  function projectItem(project, state, rate, query) {
    const open = (state.clipboardExpanded ?? []).includes(project.path);
    const info = foreignState(state, project.path);
    const head = el("button", {
      type: "button",
      class: "clip-project",
      "aria-expanded": String(open),
      dataset: { id: `project:${project.path}`, action: "project" },
    });
    head.append(
      el("span", { class: "clip-name", textContent: projectLabel(project, t) }),
      el("span", {
        class: "clip-meta",
        textContent: project.last_opened
          ? t("ui.clipboard.project_used", { date: dateText(project.last_opened) })
          : project.path,
      }),
    );
    head.addEventListener("click", () => actions.toggleProject(project.path));
    const item = el("li", { class: "clip-project-item" }, head);
    if (!open) return item;
    if (info.status === "loading" || info.status === "idle") {
      item.append(hint("ui.clipboard.project_loading"));
    } else if (info.status === "error") {
      item.append(hint("ui.clipboard.project_unreadable"));
    } else if (info.entries.length === 0) {
      item.append(hint("ui.clipboard.project_empty"));
    } else {
      const shown = filterEntries(info.entries, query, rate, t);
      item.append(
        shown.length === 0
          ? hint("ui.clipboard.no_matches")
          : list(
              project.name,
              shown.map((entry) =>
                foreignRow(entry, state, rate, {
                  from: project.path,
                  scope: project.path,
                  unshare: false,
                }),
              ),
            ),
      );
    }
    return item;
  }

  function othersView(state, rate, query) {
    const projects = state.clipboardProjects ?? [];
    const out = [hint("ui.clipboard.foreign_hint")];
    const open = button("open-project", "open-project", t("ui.clipboard.open_project"), () =>
      actions.openProject(),
    );
    if (actions.hasPicker()) {
      out.push(el("div", { class: "clip-open" }, open));
    } else {
      // A browser cannot pick a folder: type the path of the .kuulas folder instead.
      const field = el("input", {
        type: "text",
        class: "clip-path",
        value: pathDraft,
        placeholder: t("ui.clipboard.project_path_placeholder"),
        "aria-label": t("ui.clipboard.project_path_label"),
        dataset: { id: "project-path", action: "project-path" },
      });
      field.addEventListener("input", () => {
        pathDraft = field.value;
      });
      field.addEventListener("keydown", (event) => {
        event.stopPropagation();
        if (event.key === "Enter") actions.openPath(field.value);
      });
      const go = button("project-go", "project-go", t("ui.clipboard.project_show"), () =>
        actions.openPath(field.value),
      );
      out.push(el("div", { class: "clip-open" }, field, go));
    }
    if (projects.length === 0) {
      out.push(hint("ui.clipboard.others_empty"));
    } else {
      out.push(filterBox(query));
      out.push(
        el(
          "ul",
          { class: "clip-projects", "aria-label": t("ui.clipboard.projects_label") },
          ...projects.map((project) => projectItem(project, state, rate, query)),
        ),
      );
    }
    return out;
  }

  // Absolute times are Helsinki time with the zone named (the owner's rule): "19.10. 19.45 (Helsinki)".
  const dateText = (iso) => {
    const when = new Date(iso);
    if (Number.isNaN(when.getTime())) return iso;
    const day = new Intl.DateTimeFormat(getLanguage() === "fi" ? "fi-FI" : "en-GB", {
      timeZone: "Europe/Helsinki",
      day: "numeric",
      month: "numeric",
    }).format(when);
    return `${day} ${formatAbsoluteTime(when)}`;
  };

  function update(state) {
    const own = state.clipboard ?? [];
    const view = clipboardView(state);
    const choice = pasteChoice(state);
    const rate = state.project?.rate ?? 48000;
    // Whether "Paste again" can run depends on the cursor, the track and the project; the
    // answer, not the cursor, goes in the signature, so playback does not redraw the list.
    const canPaste = own.length > 0 && actions.canPasteAgain(state);
    const next = JSON.stringify([
      getLanguage(),
      view,
      own,
      state.clipboardShared,
      state.clipboardSeries,
      state.clipboardProjects,
      state.clipboardForeign,
      state.clipboardExpanded,
      rate,
      choice,
      state.clipboardSelected,
      editing,
      canPaste,
      Boolean(state.project),
      actions.hasPicker(),
      state.clipboardFilter ?? "",
      state.clipboardKeep,
      state.cartTrim,
      state.clipboardLevel,
      state.clipboardPlaying?.id ?? null,
      // "5 minutes ago" moves on by the minute, not with the cursor.
      Math.floor(actions.now() / 60),
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
    meter = null; // drawn again below if a chip plays
    // The one action bar, at the top: only the project view with entries has actions here.
    const bar = view === "project" && (state.clipboard ?? []).length > 0 ? [clearRow(state)] : [];
    const trimInput = el("input", {
      id: "cart-trim",
      type: "number",
      min: -12,
      max: 12,
      step: 0.5,
      value: String(state.cartTrim ?? 0),
      "aria-describedby": "cart-trim-help",
    });
    trimInput.addEventListener("change", () => actions.cartTrim(trimInput.value));
    root.replaceChildren(
      el("h2", { textContent: t("ui.clipboard.title") }),
      el(
        "div",
        { class: "clip-choice form-grid" },
        el(
          "label",
          { class: "form-row" },
          el("span", { class: "form-label", textContent: t("ui.clipboard.cart_trim") }),
          trimInput,
        ),
      ),
      el("p", { id: "cart-trim-help", textContent: t("ui.clipboard.cart_trim_help") }),
      ...bar,
      viewSwitch(view),
      // The two paste choices: form rows on the panel's label column (FORMS.md).
      el(
        "div",
        { class: "clip-choice form-grid" },
        el(
          "label",
          { class: "form-row" },
          el("span", { class: "form-label", textContent: t("ui.clipboard.mode") }),
          select("mode", PASTE_MODES, choice.mode, (value) => actions.choose({ pasteMode: value })),
        ),
        el(
          "label",
          { class: "form-row" },
          el("span", { class: "form-label", textContent: t("ui.clipboard.target") }),
          select("target", PASTE_TARGETS, choice.target, (value) =>
            actions.choose({ pasteTarget: value }),
          ),
        ),
      ),
    );
    const views = {
      series: () => seriesView(state, rate, query),
      shared: () => sharedView(state, rate, query),
      others: () => othersView(state, rate, query),
    };
    const body = (views[view] ?? (() => projectView(state, rate, canPaste, query)))();
    root.append(...body);
    if (keep) {
      const again = [...root.querySelectorAll("[data-id]")].find(
        (node) => node.dataset.id === keep.id && node.dataset.action === keep.action,
      );
      again?.focus();
      if (keep.caret?.[0] != null) again?.setSelectionRange?.(...keep.caret);
    }
  }

  return { update, progress };
}
