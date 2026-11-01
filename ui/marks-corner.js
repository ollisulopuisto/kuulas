// The Alku / Loppu / Pituus readout in the transport corner (docs/design/transport-corner,
// C-right). Three one-line buttons stacked at the corner's right edge:
//   click        jump to the in mark (nav.to_in), the out mark (nav.to_out), or zoom to the
//                range (view.fit_selection); nothing happens for an unset mark
//   Enter or double-click
//   Alt+click    copies the row's time to the clipboard (WP76)
//                an inline text field: Enter sets the mark (marks are UI state, no undo step),
//                Esc cancels, text that is not a time keeps the field open (red, aria-invalid)
// What each row says and what a typed time does is marks-readout.js (tested); this file only
// draws it and wires the events. The names are written beside the ruler's own in/out glyphs;
// style.css hides the words (not from screen readers) when the corner is narrow.
import { entryPatch, readoutRows } from "./marks-readout.js";

const SVG = "http://www.w3.org/2000/svg";
// The ruler's in/out flags (timeline.js drawInOut) and a double arrow for the length.
const GLYPHS = {
  in: { box: "0 0 10 12", d: ["M1 1h7L1 9z", "M1 1v10"] },
  out: { box: "0 0 10 12", d: ["M9 1H2l7 8z", "M9 1v10"] },
  length: { box: "0 0 14 12", d: ["M1 6h12M4 3 1 6l3 3M10 3l3 3-3 3"] },
};
const DOUBLE_CLICK_MS = 250;
const ROWS = [
  { which: "in", id: "mark-in", word: "ui.range.in", command: "nav.to_in" },
  { which: "out", id: "mark-out", word: "ui.range.out", command: "nav.to_out" },
  { which: "length", id: "mark-length", word: "ui.range.length", command: "view.fit_selection" },
];

function glyph(which) {
  const { box, d } = GLYPHS[which];
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", "g");
  svg.setAttribute("viewBox", box);
  svg.setAttribute("aria-hidden", "true");
  d.forEach((path, index) => {
    const node = document.createElementNS(SVG, "path");
    node.setAttribute("d", path);
    if (which === "length" || index === 1) {
      node.setAttribute("fill", "none");
      node.setAttribute("stroke", "currentColor");
      node.setAttribute("stroke-width", which === "length" ? "1.4" : "1.5");
      node.setAttribute("stroke-linecap", "round");
      node.setAttribute("stroke-linejoin", "round");
    } else {
      node.setAttribute("fill", "currentColor");
    }
    svg.append(node);
  });
  return svg;
}

/**
 * `root` holds the three buttons (#mark-in, #mark-out, #mark-length). `getState()` gives the
 * app state, `rate()` the frame rate, `format(frame, rate)` the timecode writer, `limit()` the
 * end of the edit in frames, `run(id)` runs a registered command, `patch(statePatch)` sets
 * state, `copy(text)` copies a time to the clipboard (Alt+click), `liveFrame()` is the take's
 * place while recording (null otherwise, so the length then needs both marks), `t` translates.
 */
export function createMarksCorner({
  root,
  getState,
  rate,
  format,
  limit,
  run,
  patch,
  copy,
  liveFrame,
  t,
}) {
  const buttons = new Map(ROWS.map((row) => [row.which, root.querySelector(`#${row.id}`)]));
  let editing = null; // { which, field, wrap, tip } while a field is open

  // Every read of the rows goes through here so the live length is the same on the
  // buttons, in the entry field and in an Alt+click copy.
  const rows = (state) => readoutRows(state, rate(), format, liveFrame?.() ?? null);

  function describe(row, rowData) {
    const word = t(row.word);
    const { set, text } = rowData[row.which];
    const name = set ? `${word} ${text}` : t("ui.range.unset_name", { name: word });
    let title = t("ui.range.tip_unset", { name: word });
    if (row.which === "length" && rowData.length.live)
      title = t("ui.range.tip_length_live", { name: word, time: text });
    else if (row.which === "length" && !set) title = t("ui.range.tip_length_unset", { name: word });
    else if (set) title = t(`ui.range.tip_${row.which}`, { name: word, time: text });
    return { word, set, text, name, title };
  }

  /** Redraw the three rows from the state. Safe to call on every render. */
  function render(state = getState()) {
    const rowData = rows(state);
    for (const row of ROWS) {
      const button = buttons.get(row.which);
      const { word, set, text, name, title } = describe(row, rowData);
      button.classList.toggle("set", set);
      button.classList.toggle("live", Boolean(rowData[row.which].live));
      button.setAttribute("aria-label", name);
      button.title = title;
      const key = document.createElement("span");
      key.className = "k";
      const label = document.createElement("span");
      label.className = "k-name";
      label.textContent = word;
      key.append(glyph(row.which), label);
      const value = document.createElement("span");
      value.className = "v";
      value.textContent = set ? text : "—";
      button.replaceChildren(key, value);
    }
  }

  function close(focusButton) {
    if (!editing) return;
    const { which, wrap, tip } = editing;
    editing = null;
    wrap.remove();
    tip.remove();
    const button = buttons.get(which);
    button.hidden = false;
    if (focusButton) button.focus();
  }

  function open(which) {
    if (editing) return;
    const row = ROWS.find((item) => item.which === which);
    const rowData = rows(getState());
    const word = t(row.word);
    const button = buttons.get(which);
    const wrap = document.createElement("span");
    wrap.className = "mrow editing";
    const key = document.createElement("span");
    key.className = "k";
    const label = document.createElement("span");
    label.className = "k-name";
    label.textContent = word;
    key.append(glyph(which), label);
    const field = document.createElement("input");
    field.type = "text";
    field.spellcheck = false;
    field.setAttribute("aria-label", t("ui.range.field", { name: word }));
    field.value = rowData[which].text ?? "";
    wrap.append(key, field);
    const tip = document.createElement("span");
    tip.className = "edit-tip";
    tip.textContent = t("ui.range.edit_hint");
    button.hidden = true;
    button.after(wrap);
    root.append(tip);
    editing = { which, field, wrap, tip };
    field.focus();
    field.select();

    const apply = () => {
      const current = getState();
      const result = entryPatch(which, field.value, current, rate(), limit());
      if (!result.ok) return false;
      patch({ ...result.patch, rangeTracks: new Set() });
      return true;
    };
    field.addEventListener("keydown", (event) => {
      // Typing must not reach the keymap (1, 2, I, O, F ... are commands).
      event.stopPropagation();
      if (event.key === "Enter") {
        event.preventDefault();
        if (apply()) {
          close(true);
        } else {
          field.setAttribute("aria-invalid", "true");
          wrap.classList.add("invalid");
          field.title = t("ui.range.invalid");
          tip.textContent = t("ui.range.invalid");
        }
      } else if (event.key === "Escape") {
        event.preventDefault();
        close(true);
      } else if (field.getAttribute("aria-invalid")) {
        field.removeAttribute("aria-invalid");
        wrap.classList.remove("invalid");
        tip.textContent = t("ui.range.edit_hint");
      }
    });
    // Leaving the field keeps a readable time and drops anything else.
    field.addEventListener("blur", () => {
      if (editing?.field !== field) return;
      apply();
      close(false);
    });
  }

  for (const row of ROWS) {
    const button = buttons.get(row.which);
    // A jump is harmless twice, but a zoom is not: the length waits out a possible
    // double-click (the field is what the second click asks for).
    let pending = null;
    button.addEventListener("click", (event) => {
      if (editing) return;
      if (event.altKey) {
        // Alt+click copies the row's time (WP76); a plain click keeps jumping to the mark.
        const { set, text } = rows(getState())[row.which];
        if (set) copy(text);
        return;
      }
      if (row.which !== "length" || event.detail === 0) return run(row.command);
      clearTimeout(pending);
      pending = setTimeout(() => run(row.command), DOUBLE_CLICK_MS);
    });
    button.addEventListener("dblclick", (event) => {
      event.preventDefault();
      clearTimeout(pending);
      open(row.which);
    });
    // Enter types a time; Space still clicks (jumps).
    button.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.metaKey || event.ctrlKey || event.altKey) return;
      event.preventDefault();
      event.stopPropagation();
      open(row.which);
    });
  }

  return { render, open };
}
