// The toolbar rail (WP86, docs/design/TOOLBAR.md): a vertical strip left of the track headers.
// toolbar-items.js says what the buttons are; this draws them and runs the command a click names.
// The buttons are created once per layout and only their text, tip and enabled state are updated,
// in place: a button never moves because something else changed. Updates are coalesced into one
// frame and skipped when nothing the user can see has changed.
import { setIcon } from "./icons.js";
import { RAIL_SEARCH, toolbarItems } from "./toolbar-items.js";
import { dropIndex, stepButton } from "./toolbar-model.js";

export function createToolbarRail({
  root,
  editor,
  registry,
  getState,
  t,
  keyOf,
  run,
  onContext = null,
  onMove = null,
  layout,
  mode,
  visible,
}) {
  const current = { layout, mode, visible };
  const buttons = new Map();
  let builtFor = "";
  let drawn = "";
  let queued = false;
  let refocus = null; // the id whose button gets the focus back after a rebuild
  const DRAG_PX = 5;

  // The fixed search button: above the layout's buttons, not one of them (no drag, no menu).
  const search = document.createElement("button");
  search.type = "button";
  search.className = "button ghost rail-search";
  const searchLabel = document.createElement("span");
  searchLabel.className = "rail-label";
  search.append(searchLabel);

  function build() {
    buttons.clear();
    const nodes = current.layout.map((id) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button ghost rail-btn";
      button.dataset.id = id;
      const label = document.createElement("span");
      label.className = "rail-label";
      const badge = document.createElement("span");
      badge.className = "rail-badge";
      button.append(label, badge);
      buttons.set(id, button);
      return button;
    });
    root.replaceChildren(search, ...nodes);
    builtFor = current.layout.join("\n");
  }

  function refresh() {
    editor.dataset.rail = current.visible ? current.mode : "off";
    root.hidden = !current.visible;
    if (!current.visible) return;
    const items = toolbarItems({ layout: current.layout, registry, state: getState(), t, keyOf });
    const signature = JSON.stringify([
      current.mode,
      items.map((item) => [item.id, item.label, item.tip, item.enabled, item.icon, item.badge]),
    ]);
    if (signature === drawn) return;
    {
      const name = t(RAIL_SEARCH.label);
      const key = keyOf(RAIL_SEARCH.command);
      searchLabel.textContent = name;
      search.dataset.tip = key ? `${t("ui.search.label")} (${key})` : t("ui.search.label");
      search.setAttribute("aria-label", name);
      setIcon(search, RAIL_SEARCH.icon);
      searchLabel.classList.toggle("visually-hidden", current.mode !== "labels");
    }
    drawn = signature;
    if (current.layout.join("\n") !== builtFor) {
      build();
      if (refocus) buttons.get(refocus)?.focus();
      refocus = null;
    }
    for (const item of items) {
      const button = buttons.get(item.id);
      button.querySelector(".rail-label").textContent = item.label;
      button.dataset.tip = item.tip;
      const badge = button.querySelector(".rail-badge");
      badge.textContent = item.badge ?? "";
      badge.hidden = item.badge === null;
      button.setAttribute("aria-label", item.badge ? `${item.label} (${item.badge})` : item.label);
      button.setAttribute("aria-disabled", String(!item.enabled));
      if (item.icon) setIcon(button, item.icon);
      else delete button.dataset.icon;
      // A button without an icon always shows its text, so it is never empty.
      const showText = current.mode === "labels" || !item.icon;
      button.querySelector(".rail-label").classList.toggle("visually-hidden", !showText);
    }
  }

  function update() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      refresh();
    });
  }

  search.addEventListener("click", () => run(RAIL_SEARCH.command));

  let swallowClick = false;
  root.addEventListener("click", (event) => {
    if (swallowClick) {
      swallowClick = false;
      return;
    }
    const button = event.target.closest?.(".rail-btn");
    if (!button || button.getAttribute("aria-disabled") === "true") return;
    run(button.dataset.id);
  });

  // Drag to reorder: the user's own hand is the only thing that moves a button. A press that
  // moves less than DRAG_PX is a click; Escape or a drop outside the rail changes nothing.
  root.addEventListener("pointerdown", (event) => {
    const button = event.target.closest?.(".rail-btn");
    if (!button || !onMove || event.button !== 0) return;
    const id = button.dataset.id;
    const startY = event.clientY;
    let dragging = false;
    let to = 0;
    const marker = document.createElement("div");
    marker.className = "rail-drop";
    const from = current.layout.indexOf(id);

    function place(y) {
      const nodes = [...root.querySelectorAll(".rail-btn")];
      const mids = nodes.map((node) => {
        const box = node.getBoundingClientRect();
        return box.top + box.height / 2;
      });
      to = dropIndex(mids, from, y);
      const others = nodes.filter((node) => node !== button);
      const rootBox = root.getBoundingClientRect();
      const edge =
        to < others.length
          ? others[to].getBoundingClientRect().top
          : (others.at(-1)?.getBoundingClientRect().bottom ?? rootBox.top);
      marker.style.top = `${edge - rootBox.top + root.scrollTop - 1}px`;
    }
    function finish() {
      root.removeEventListener("pointermove", move);
      root.removeEventListener("pointerup", up);
      root.removeEventListener("pointercancel", cancel);
      document.removeEventListener("keydown", key, true);
      marker.remove();
      button.classList.remove("dragging");
      if (button.hasPointerCapture?.(event.pointerId))
        button.releasePointerCapture(event.pointerId);
    }
    function move(e) {
      if (!dragging) {
        if (Math.abs(e.clientY - startY) < DRAG_PX) return;
        dragging = true;
        button.classList.add("dragging");
        root.append(marker);
      }
      place(e.clientY);
    }
    function up() {
      finish();
      if (!dragging) return;
      swallowClick = true;
      setTimeout(() => {
        swallowClick = false;
      }, 0);
      if (to !== from) {
        refocus = id;
        onMove(id, to);
      }
    }
    function cancel() {
      finish();
    }
    function key(e) {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      finish();
      if (dragging) {
        swallowClick = true;
        setTimeout(() => {
          swallowClick = false;
        }, 0);
      }
    }
    button.setPointerCapture?.(event.pointerId);
    root.addEventListener("pointermove", move);
    root.addEventListener("pointerup", up);
    root.addEventListener("pointercancel", cancel);
    document.addEventListener("keydown", key, true);
  });

  // Alt+Up / Alt+Down on a focused button moves it one place.
  root.addEventListener("keydown", (event) => {
    const button = event.target.closest?.(".rail-btn");
    if (!button || !onMove || !event.altKey) return;
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    const id = button.dataset.id;
    const next = stepButton(current.layout, id, event.key === "ArrowUp" ? -1 : 1);
    if (next === current.layout) return;
    refocus = id;
    onMove(id, next.indexOf(id));
  });

  // Right-click on a button: the owner of the menu (Remove from toolbar) is app.js.
  root.addEventListener("contextmenu", (event) => {
    const button = event.target.closest?.(".rail-btn");
    if (!button || !onContext) return;
    event.preventDefault();
    onContext(button.dataset.id, event);
  });

  return {
    update,
    layout: () => current.layout,
    setLayout(next) {
      current.layout = next;
      drawn = "";
      update();
    },
    setMode(next) {
      current.mode = next;
      drawn = "";
      update();
    },
    setVisible(next) {
      current.visible = next;
      drawn = "";
      update();
    },
  };
}
