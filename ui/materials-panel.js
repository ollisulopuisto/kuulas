// One sidebar destination, two distinct data models. Existing panels keep their
// own actions, filters and persistence; switching never converts or copies data.
import { t } from "./i18n.js";
export function createMaterialsPanel({ root, select }) {
  const bar = document.createElement("div");
  bar.className = "mat-filters materials-scopes";
  bar.setAttribute("role", "group");
  bar.setAttribute("aria-label", t("ui.tabs.material"));
  const buttons = new Map();
  for (const scope of ["recordings", "clipboard"]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button";
    button.dataset.scope = scope;
    button.addEventListener("click", () => select(scope));
    buttons.set(scope, button);
    bar.append(button);
  }
  const title = document.createElement("h2");
  title.textContent = t("ui.tabs.material");
  root.prepend(title, bar);
  return {
    update(state) {
      const scope = state.materialsScope === "clipboard" ? "clipboard" : "recordings";
      for (const [name, button] of buttons) {
        button.textContent = t(`ui.materials.scope.${name}`);
        button.setAttribute("aria-pressed", String(name === scope));
      }
      root.querySelector("#materials-recordings").hidden = scope !== "recordings";
      root.querySelector("#panel-clipboard").hidden = scope !== "clipboard";
    },
  };
}
