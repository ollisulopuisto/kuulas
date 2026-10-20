// The small text prompt for a narration placeholder (WP43): a textarea with a live
// "12 words, about 5 s" under it, so the length is seen while typing. Enter saves,
// Shift+Enter is a new line, Escape cancels. The words and seconds come from
// placeholders-model.js, the same count the server uses.
import { estimatePreview } from "./placeholders-model.js";

/** `root`: the hidden container in index.html. `t` translates. -> { prompt }. */
export function createPlaceholderEditor({ root, t }) {
  let finish = null;

  function close(value) {
    root.hidden = true;
    root.replaceChildren();
    const done = finish;
    finish = null;
    done?.(value);
  }

  /** Ask for the text; resolves with the text, or null when cancelled. One at a time. */
  function prompt({ text = "", rate }) {
    if (finish) close(null);
    root.replaceChildren();
    const title = document.createElement("h3");
    title.id = "placeholder-editor-title";
    title.textContent = t("ui.placeholders.editor.title");
    const label = document.createElement("label");
    label.className = "placeholder-field";
    const caption = document.createElement("span");
    caption.textContent = t("ui.placeholders.editor.label");
    const area = document.createElement("textarea");
    area.rows = 4;
    area.value = text;
    label.append(caption, area);
    const readout = document.createElement("p");
    readout.className = "placeholder-estimate";
    readout.setAttribute("aria-live", "polite");
    const save = document.createElement("button");
    save.type = "button";
    save.className = "button primary";
    save.textContent = t("ui.placeholders.editor.save");
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "button";
    cancel.textContent = t("ui.placeholders.editor.cancel");
    const actions = document.createElement("div");
    actions.className = "import-actions";
    actions.append(cancel, save); // the primary action last, as in every dialog

    const refresh = () => {
      const { words, seconds } = estimatePreview(area.value, rate);
      readout.textContent =
        words === 0
          ? t("ui.placeholders.editor.empty")
          : t("ui.placeholders.editor.estimate", { words, seconds });
      save.disabled = words === 0;
    };
    area.addEventListener("input", refresh);
    area.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        close(null);
      } else if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        event.stopPropagation();
        if (!save.disabled) close(area.value);
      }
    });
    save.addEventListener("click", () => close(area.value));
    cancel.addEventListener("click", () => close(null));
    root.append(title, label, readout, actions);
    refresh();
    root.hidden = false;
    area.focus();
    area.setSelectionRange(area.value.length, area.value.length);
    return new Promise((resolve) => {
      finish = resolve;
    });
  }

  return { prompt };
}
