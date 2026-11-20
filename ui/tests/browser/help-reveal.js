import { createHelpPanel } from "../../help-panel.js";
import { initI18n } from "../../i18n.js";

await initI18n({ language: "en" });
const root = document.querySelector("#help");
const inspector = document.querySelector("#inspector");
let panel = "history";
const help = createHelpPanel({
  root,
  getContext: () => ({ selection: 1 }),
  keymap: () => [],
  commands: () => [],
  format: String,
  runCommand: () => {},
  fetchText: async (path) => (await fetch(`/${path}`)).text(),
  revealPanel: (name) => {
    help.close();
    panel = name;
    inspector.hidden = false;
    inspector.focus();
  },
});
await help.openTopic("clip");
root.querySelector('[data-show="inspector"]').click();
const target = document.querySelector('[data-help-id="inspector"]');
const result = {
  panel,
  visible: target.getBoundingClientRect().width > 0 && target.getBoundingClientRect().height > 0,
  helpClosed: !help.isOpen(),
  disclosureOpen: target.closest("details").open,
  highlighted: target.classList.contains("help-highlight"),
  focusedPanel: document.activeElement === inspector,
};
if (new URLSearchParams(location.search).has("visual"))
  document.querySelector("#result").hidden = true;
document.querySelector("#result").textContent = JSON.stringify(result);
