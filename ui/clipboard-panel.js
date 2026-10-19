// The Clipboard tab (WP46, WP65): three views behind a segmented control. *This project* is
// the project's own clipboard, newest first, with each entry's name, metadata line, Share star,
// play, "Paste again", rename and delete. *Shared* lists the entries marked as worth sharing,
// from every project. *Other projects* lists the recent projects (click one to read its
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
  foreignState,
  keepCount,
  PASTE_MODES,
  PASTE_TARGETS,
  pasteChoice,
  projectLabel,
} from "./clipboard.js";
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
 * `actions`: select(id), preview(id), filter(text), rename(id, name), remove(id), pasteAgain(id),
 * share(id, on), view(name), choose({ pasteMode } | { pasteTarget }), keep(n), clearOld(),
 * toggleProject(path), openProject(), openPath(path), hasPicker() -> boolean,
 * adopt(entry, from), pasteHere(entry, from), now() -> UTC epoch seconds,
 * canPasteAgain(state) -> boolean.
 */
export function createClipboardPanel({ root, actions }) {
  let signature = "";
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
    // The star: marked entries are listed under Shared by every project.
    const star = el("button", {
      type: "button",
      class: "button ghost clip-star",
      textContent: entry.shared ? "★" : "☆",
      title: t(entry.shared ? "ui.clipboard.share_on" : "ui.clipboard.share_off"),
      "aria-label": t("ui.clipboard.share"),
      "aria-pressed": String(Boolean(entry.shared)),
      dataset: { id: entry.id, action: "share" },
    });
    star.addEventListener("click", () => actions.share(entry.id, !entry.shared));
    const buttons = el(
      "span",
      { class: "clip-actions" },
      star,
      button(entry.id, "preview", t("ui.clipboard.preview"), () => actions.preview(entry.id)),
      button(entry.id, "paste", t("ui.clipboard.paste_again"), () => actions.pasteAgain(entry.id), {
        disabled: !canPaste,
      }),
      button(entry.id, "rename", t("ui.clipboard.rename"), () => {
        editing = entry.id;
        signature = "";
        update(state);
        root.querySelector(".clip-rename")?.focus();
      }),
      button(entry.id, "delete", t("ui.clipboard.delete"), () => actions.remove(entry.id)),
    );
    return el(
      "li",
      { class: "clip-entry", dataset: { id: entry.id, selected: String(selected) } },
      name,
      buttons,
    );
  }

  /**
   * An entry that is not this project's own (shared, or read from another project): read-only,
   * so no play button (it plays once it is copied here), but it can be adopted. `from` is the
   * folder of the project it was read from ("" for the shared list); `scope` keeps ids unique.
   */
  function foreignRow(entry, state, rate, { from, scope, unshare }) {
    const id = `${scope}:${entry.id}`;
    const canPaste = Boolean(state.project);
    const buttons = el(
      "span",
      { class: "clip-actions" },
      button(id, "paste-here", t("ui.clipboard.paste_here"), () => actions.pasteHere(entry, from), {
        disabled: !canPaste,
      }),
      button(id, "copy-here", t("ui.clipboard.copy_here"), () => actions.adopt(entry, from), {
        disabled: !canPaste,
      }),
    );
    if (unshare) {
      buttons.append(
        button(id, "unshare", t("ui.clipboard.unshare"), () => actions.share(entry.id, false)),
      );
    }
    return el(
      "li",
      { class: "clip-entry", dataset: { id, foreign: "true" } },
      el("span", { class: "clip-main" }, ...labels(entry, rate)),
      buttons,
    );
  }

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
      event.stopPropagation(); // typing a name is not a shortcut
      if (event.key === "Escape" && filter.value) {
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
    return el(
      "div",
      { class: "clip-clear" },
      el("span", { textContent: t("ui.clipboard.keep_label") }),
      field,
      clear,
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
      clearRow(state),
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
    root.replaceChildren(
      el("h2", { textContent: t("ui.clipboard.title") }),
      viewSwitch(view),
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
    const body =
      view === "shared"
        ? sharedView(state, rate, query)
        : view === "others"
          ? othersView(state, rate, query)
          : projectView(state, rate, canPaste, query);
    root.append(...body);
    if (keep) {
      const again = [...root.querySelectorAll("[data-id]")].find(
        (node) => node.dataset.id === keep.id && node.dataset.action === keep.action,
      );
      again?.focus();
      if (keep.caret?.[0] != null) again?.setSelectionRange?.(...keep.caret);
    }
  }

  return { update };
}
