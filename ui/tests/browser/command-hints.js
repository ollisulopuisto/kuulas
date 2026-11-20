import { applyCommandShortcuts } from "../../command-shortcuts.js";
import { initI18n, t } from "../../i18n.js";
import { installTooltips, REST_MS } from "../../tooltip.js";

await initI18n({ language: "fi" });
applyCommandShortcuts(
  document,
  [{ id: "view.fit", labelKey: "cmd.view.fit", raw: ["F8"] }],
  "mac",
  { t },
);
installTooltips();
const button = document.querySelector("button");
button.dispatchEvent(new PointerEvent("pointermove", { bubbles: true, clientX: 90, clientY: 65 }));
await new Promise((resolve) => setTimeout(resolve, REST_MS + 10));
const box = document.querySelector('[role="tooltip"]');
const result = {
  text: box.textContent,
  visible: !box.hidden,
  correct: box.textContent === button.dataset.tip,
};
if (new URLSearchParams(location.search).has("visual"))
  document.querySelector("#result").hidden = true;
document.querySelector("#result").textContent = JSON.stringify(result);
