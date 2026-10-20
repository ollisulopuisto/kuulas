// A plug-in field of the automixer dialog: chips for the accepted plug-ins (the name shown,
// the full path in the title, the path is the value), a text input with a suggestion
// listbox while typing. The matching is pure (plugin-match.js); this file is the DOM.
//
// Keys, in the input: Down/Up move in the list, Enter and Tab accept, Esc closes the list
// (and only that: the dialog stays open, so the event is stopped), Backspace on an empty
// input removes the last chip. When nothing is installed (or the scan failed) the field is
// plain text: its words are the values.

import { parseWords } from "./automix-model.js";
import { highlightRuns, labelFor, matchPlugins, resolveTyped } from "./plugin-match.js";

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

let counter = 0;

/**
 * `t` translates; `placeholder` is the hint shown while the field is empty (never a value).
 * Returns { element, input, items(), setItems(paths), setInstalled(list), setDisabled(bool),
 * unmatched() }. `onChange()` is called when the chips or the text change.
 */
export function createPluginField({ t, placeholder, onChange = () => {} }) {
  counter += 1;
  const listId = `plugin-list-${counter}`;
  const element = el("div", "plugin-field");
  const chips = el("span", "plugin-chips");
  const input = el("input");
  input.type = "text";
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", listId);
  const list = el("ul", "plugin-list");
  list.id = listId;
  list.setAttribute("role", "listbox");
  list.hidden = true;
  element.append(chips, input, list);

  let installed = [];
  let paths = [];
  let shown = [];
  let active = -1;
  let disabled = false;

  const open = () => !list.hidden;
  function close() {
    list.hidden = true;
    active = -1;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }
  function setActive(index) {
    active = index;
    input.setAttribute("aria-expanded", "true");
    list.querySelectorAll("[role=option]").forEach((node, i) => {
      node.setAttribute("aria-selected", String(i === active));
      if (i === active) {
        input.setAttribute("aria-activedescendant", node.id);
        node.scrollIntoView?.({ block: "nearest" });
      }
    });
  }
  function renderList() {
    const query = input.value;
    shown = installed.length > 0 && !disabled ? matchPlugins(query, installed) : [];
    list.replaceChildren();
    if (shown.length === 0) return close();
    shown.forEach((plugin, i) => {
      const option = el("li", "plugin-option");
      option.id = `${listId}-${i}`;
      option.setAttribute("role", "option");
      option.title = plugin.path;
      const name = el("span", "plugin-name");
      for (const run of highlightRuns(plugin.name, plugin.indices)) {
        name.append(run.hit ? el("mark", "", run.text) : document.createTextNode(run.text));
      }
      option.append(name, el("span", "plugin-format", plugin.format));
      // mousedown, not click: the input keeps focus, so its blur does not close the list first
      option.addEventListener("mousedown", (event) => {
        event.preventDefault();
        accept(plugin);
      });
      list.append(option);
    });
    list.hidden = false;
    setActive(0);
  }

  function renderChips() {
    chips.replaceChildren();
    for (const path of paths) {
      const chip = el("span", "chip plugin-chip");
      chip.title = path;
      chip.append(el("span", "", labelFor(path, installed)));
      const remove = el("button", "button ghost icon plugin-remove");
      remove.type = "button";
      remove.dataset.icon = "close";
      remove.disabled = disabled;
      const label = t("ui.automix.plugin_remove", { name: labelFor(path, installed) });
      remove.setAttribute("aria-label", label);
      remove.title = label;
      remove.addEventListener("click", () => {
        paths = paths.filter((p) => p !== path);
        renderChips();
        onChange();
        input.focus();
      });
      chip.append(remove);
      chips.append(chip);
    }
    // The hint is for an empty field only: with a chip in it, it would read as another value.
    input.placeholder = paths.length === 0 ? placeholder : "";
  }

  function addPath(path) {
    if (!paths.includes(path)) paths = [...paths, path];
    input.value = "";
    close();
    renderChips();
    onChange();
  }
  function accept(plugin) {
    addPath(plugin.path);
  }
  /** Turn the typed text into a chip when it stands for a plug-in or a path. */
  function commit() {
    const typed = resolveTyped(input.value, installed);
    if (typed.kind === "match") accept(typed.plugin);
    else if (typed.kind === "path") addPath(typed.path);
  }

  input.addEventListener("input", () => {
    renderList();
    onChange();
  });
  input.addEventListener("keydown", (event) => {
    const stop = () => {
      event.preventDefault();
      event.stopPropagation();
    };
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!open()) {
        renderList();
        if (!open()) return;
        stop();
        return;
      }
      stop();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((active + step + shown.length) % shown.length);
    } else if ((event.key === "Enter" || event.key === "Tab") && open() && active >= 0) {
      stop();
      accept(shown[active]);
    } else if (event.key === "Escape" && open()) {
      stop();
      close();
    } else if (event.key === "Backspace" && input.value === "" && paths.length > 0) {
      paths = paths.slice(0, -1);
      renderChips();
      onChange();
    }
  });
  input.addEventListener("blur", () => {
    close();
    commit();
  });

  renderChips();
  return {
    element,
    input,
    /** The values: the chips' paths, plus what is typed (a path, the best match of a name,
     * or the plain words when nothing is installed). A name nothing matches is left out. */
    items() {
      const typed = resolveTyped(input.value, installed);
      if (typed.kind === "path") return [...paths, typed.path];
      if (typed.kind === "match") return [...paths, typed.plugin.path];
      if (typed.kind === "plain") return [...paths, ...parseWords(typed.text)];
      return [...paths];
    },
    setItems(values) {
      paths = [...values];
      input.value = "";
      close();
      renderChips();
    },
    setInstalled(list_) {
      installed = Array.isArray(list_) ? list_ : [];
      renderChips();
    },
    setDisabled(value) {
      disabled = value;
      input.disabled = value;
      if (value) close();
      renderChips();
    },
    /** Typed text no installed plug-in matches (a warning; Mix waits). */
    unmatched() {
      return resolveTyped(input.value, installed).kind === "none";
    },
  };
}
