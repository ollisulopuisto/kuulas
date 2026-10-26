// The toolbar rail (WP86, docs/design/TOOLBAR.md): a vertical strip left of the track headers.
// toolbar-items.js says what the buttons are; this draws them and runs the command a click names.
// The buttons are created once per layout and only their text, tip and enabled state are updated,
// in place: a button never moves because something else changed. Updates are coalesced into one
// frame and skipped when nothing the user can see has changed.
import { setIcon } from "./icons.js";
import { toolbarItems } from "./toolbar-items.js";

export function createToolbarRail({
  root,
  editor,
  registry,
  getState,
  t,
  keyOf,
  run,
  layout,
  mode,
  visible,
}) {
  const current = { layout, mode, visible };
  const buttons = new Map();
  let builtFor = "";
  let drawn = "";
  let queued = false;

  function build() {
    buttons.clear();
    const nodes = current.layout.map((id) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button ghost rail-btn";
      button.dataset.id = id;
      const label = document.createElement("span");
      label.className = "rail-label";
      button.append(label);
      buttons.set(id, button);
      return button;
    });
    root.replaceChildren(...nodes);
    builtFor = current.layout.join("\n");
  }

  function refresh() {
    editor.dataset.rail = current.visible ? current.mode : "off";
    root.hidden = !current.visible;
    if (!current.visible) return;
    const items = toolbarItems({ layout: current.layout, registry, state: getState(), t, keyOf });
    const signature = JSON.stringify([
      current.mode,
      items.map((item) => [item.id, item.label, item.tip, item.enabled, item.icon]),
    ]);
    if (signature === drawn) return;
    drawn = signature;
    if (current.layout.join("\n") !== builtFor) build();
    for (const item of items) {
      const button = buttons.get(item.id);
      button.querySelector(".rail-label").textContent = item.label;
      button.dataset.tip = item.tip;
      button.setAttribute("aria-label", item.label);
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

  root.addEventListener("click", (event) => {
    const button = event.target.closest?.(".rail-btn");
    if (!button || button.getAttribute("aria-disabled") === "true") return;
    run(button.dataset.id);
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
