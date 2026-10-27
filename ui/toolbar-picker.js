import { matchCommand } from "./command-search.js";
import { enhanceDialog } from "./dialog-keys.js";

/** Pinning does not execute a command: actions unavailable in this selection remain addable. */
export function toolbarChoices({ entries, layout, registry, label, query }) {
  const seen = new Set(layout);
  const rows = [];
  for (const entry of entries) {
    if (seen.has(entry.id) || !registry.has(entry.id) || registry.status(entry.id) !== "ready")
      continue;
    seen.add(entry.id);
    const name = label(entry.labelKey);
    const hint = label(`${entry.labelKey}.hint`);
    const match = query.trim() ? matchCommand({ names: [name], hints: [hint] }, query) : null;
    if (query.trim() && !match) continue;
    rows.push({ id: entry.id, name, score: match?.score ?? 0 });
  }
  return rows.sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
}

export function createToolbarPicker({ t, choices, add }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet toolbar-picker";
  const title = document.createElement("h2");
  title.id = "toolbar-picker-title";
  dialog.setAttribute("aria-labelledby", title.id);
  const note = document.createElement("p");
  note.className = "form-note";
  const input = document.createElement("input");
  input.type = "search";
  input.className = "toolbar-picker-search";
  const list = document.createElement("div");
  list.className = "toolbar-picker-list";
  const empty = document.createElement("p");
  empty.className = "form-note";
  const footer = document.createElement("div");
  footer.className = "cheatsheet-footer";
  const close = document.createElement("button");
  close.type = "button";
  close.className = "button block primary";
  close.dataset.dialogCancel = "";
  footer.append(close);
  dialog.append(title, note, input, list, empty, footer);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });
  let returnTo = null;
  function draw() {
    title.textContent = t("cmd.view.toolbar_add");
    note.textContent = t("ui.rail.pick_note");
    input.placeholder = t("ui.rail.pick_search");
    input.setAttribute("aria-label", t("ui.rail.pick_search"));
    close.textContent = t("ui.rail.close");
    const rows = choices(input.value);
    list.replaceChildren(
      ...rows.map((row) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "button toolbar-picker-choice";
        button.dataset.id = row.id;
        button.textContent = row.name;
        button.addEventListener("click", () => {
          add(row.id);
          dialog.close();
        });
        return button;
      }),
    );
    empty.hidden = rows.length > 0;
    empty.textContent = t("ui.rail.pick_empty");
  }
  input.addEventListener("input", draw);
  input.addEventListener("keydown", (event) => {
    if (!["Enter", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    const first = list.querySelector("button");
    if (event.key === "Enter") first?.click();
    else first?.focus();
  });
  list.addEventListener("keydown", (event) => {
    if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    const buttons = [...list.children];
    const index = buttons.indexOf(document.activeElement);
    const next = index + (event.key === "ArrowDown" ? 1 : -1);
    (buttons[next] ?? input).focus();
  });
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => returnTo?.isConnected && returnTo.focus());
  return {
    open() {
      returnTo = document.activeElement;
      input.value = "";
      draw();
      dialog.showModal();
      input.focus();
    },
  };
}
