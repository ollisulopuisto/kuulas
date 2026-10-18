// The Markers tab (WP19h): every marker, chapter and region by start time, with its name,
// time, kind and Jump, Rename, Chapter (toggle) and Delete. At the top: add a marker, and the
// three exports. The panel only draws and reports; what a click does is app.js's (actions).
import { formatClock, formatNumber, getLanguage, t } from "./i18n.js";
import { LEFT_OFF_ID, leftOffRow, leftOffText } from "./left-off.js";
import { markerRows } from "./markers-model.js";

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
 * `actions`: jump(id), rename(id, name), remove(id), setKind(id, kind), run(commandId),
 * can(commandId, state) -> boolean.
 */
export function createMarkersPanel({ root, actions }) {
  let signature = "";
  let editing = null; // the id being renamed
  let last = null; // the state of the last update, for redraws from inside the panel
  const redraw = () => last && update(last);

  function row(item, selected) {
    let name;
    if (editing === item.id) {
      name = el("input", {
        type: "text",
        class: "clip-rename",
        value: item.name,
        "aria-label": t("ui.markers.rename_label"),
        dataset: { id: item.id, action: "rename-input" },
      });
      name.addEventListener("keydown", (event) => {
        event.stopPropagation();
        if (event.key === "Enter") {
          editing = null;
          actions.rename(item.id, name.value);
        } else if (event.key === "Escape") {
          editing = null;
          signature = "";
          redraw();
        }
      });
      name.addEventListener("blur", () => {
        if (editing !== item.id) return;
        editing = null;
        actions.rename(item.id, name.value);
      });
    } else {
      const length =
        item.length === null
          ? ""
          : ` · ${t("ui.markers.length", { seconds: formatNumber(item.length, { digits: 1 }) })}`;
      name = el(
        "button",
        {
          type: "button",
          class: "clip-main",
          "aria-pressed": String(selected),
          title: t("ui.markers.jump", { name: item.name }),
          dataset: { id: item.id, action: "jump" },
        },
        el("span", { class: "clip-name", textContent: item.name }),
        el("span", {
          class: "clip-meta",
          textContent: `${formatClock(item.seconds, 1)} · ${t(`ui.markers.kind.${item.kind}`)}${length}`,
        }),
      );
      name.addEventListener("click", () => actions.jump(item.id));
    }
    const button = (action, label, onClick, extra = {}) => {
      const node = el("button", {
        type: "button",
        class: "button ghost",
        textContent: label,
        dataset: { id: item.id, action },
        ...extra,
      });
      node.addEventListener("click", onClick);
      return node;
    };
    const buttons = el(
      "span",
      { class: "clip-actions" },
      button("rename", t("ui.markers.rename"), () => {
        editing = item.id;
        signature = "";
        redraw();
        root.querySelector(".clip-rename")?.focus();
      }),
    );
    if (item.kind !== "region") {
      buttons.append(
        button(
          "chapter",
          t("ui.markers.kind.chapter"),
          () => actions.setKind(item.id, item.kind === "chapter" ? "marker" : "chapter"),
          { "aria-pressed": String(item.kind === "chapter") },
        ),
      );
    }
    buttons.append(button("delete", t("ui.markers.delete"), () => actions.remove(item.id)));
    return el(
      "li",
      { class: "clip-entry", dataset: { id: item.id, selected: String(selected) } },
      name,
      buttons,
    );
  }

  // The automatic "left off" row, pinned first: not a project marker, so no rename, chapter
  // or delete; the whole row is one button (click or Enter goes there).
  function leftOffEntry(item, rate) {
    const words = { t, clock: (seconds) => formatClock(seconds, 1), language: getLanguage() };
    const text = leftOffText({ frame: item.frame, savedAt: item.savedAt }, rate, words, "row");
    const main = el("button", {
      type: "button",
      class: "clip-main",
      title: t("ui.resume.jump"),
      dataset: { id: LEFT_OFF_ID, action: "jump" },
    });
    main.append(
      el("span", { class: "clip-name", textContent: t("ui.resume.flag") }),
      el("span", { class: "clip-meta", textContent: text }),
    );
    main.addEventListener("click", () => actions.jumpLeftOff());
    return el("li", { class: "clip-entry", dataset: { id: LEFT_OFF_ID, pinned: "true" } }, main);
  }

  const toolbarButton = (command, label, state) => {
    const node = el("button", {
      type: "button",
      class: "button",
      textContent: label,
      disabled: !actions.can(command, state),
      dataset: { action: command },
    });
    node.addEventListener("click", () => actions.run(command));
    return node;
  };

  function update(state) {
    const rate = state.project?.rate ?? 48000;
    const rows = markerRows(state.project?.markers, rate);
    const can = [
      "marker.add",
      "export.chapters_text",
      "export.chapters_json",
      "export.regions",
    ].map((id) => actions.can(id, state));
    const pinned = leftOffRow(state.leftOff, rate);
    const next = JSON.stringify([
      getLanguage(),
      rows,
      rate,
      state.markerSelected,
      editing,
      can,
      pinned,
    ]);
    if (next === signature) return;
    signature = next;
    const active = document.activeElement;
    const keep =
      root.contains(active) && active.dataset?.id
        ? { id: active.dataset.id, action: active.dataset.action }
        : null;
    root.replaceChildren(
      el("h2", { textContent: t("ui.markers.title") }),
      el(
        "div",
        { class: "clip-choice" },
        toolbarButton("marker.add", t("cmd.marker.add"), state),
        toolbarButton("export.chapters_text", t("cmd.export.chapters_text"), state),
        toolbarButton("export.chapters_json", t("cmd.export.chapters_json"), state),
        toolbarButton("export.regions", t("cmd.export.regions"), state),
      ),
    );
    if (rows.length === 0 && !pinned) {
      root.append(el("p", { class: "hint", textContent: t("ui.markers.empty") }));
    } else {
      root.append(
        el(
          "ul",
          { class: "clip-list", "aria-label": t("ui.markers.list_label") },
          ...(pinned ? [leftOffEntry(pinned, rate)] : []),
          ...rows.map((item) => row(item, state.markerSelected === item.id)),
        ),
      );
    }
    if (keep) {
      root
        .querySelector(`[data-id="${CSS.escape(keep.id)}"][data-action="${keep.action}"]`)
        ?.focus();
    }
  }

  return {
    update(state) {
      last = state;
      update(state);
    },
  };
}
