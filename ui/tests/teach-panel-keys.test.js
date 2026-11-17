// Teaching the two-step panel keys (owner, 2026-11-17): the status bar says what a bare
// number does right after Markers or Clipboard opens, and corrects a dead number press
// elsewhere, until the user has shown the pattern once (the core-loop panelkeys row).

import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { resolveHints } from "../hints.js";
import { resolveKeymap } from "../keymap-config.js";
import { DEFAULT_KEYMAP, STATUS_HINTS } from "../keymap-default.js";
import { createStatusTeacher, teachForCommand, teachForDeadDigit } from "../status-teach.js";

const NOT_TAUGHT = { tried: [], steps: {} };
const TAUGHT = { tried: ["panelkeys"], steps: {} };

describe("teachForCommand", () => {
  test("opening Markers or Clipboard teaches until the row has ticked", () => {
    assert.equal(teachForCommand("panel.show_markers", NOT_TAUGHT), "ui.teach.open_markers");
    assert.equal(teachForCommand("panel.show_clipboard", NOT_TAUGHT), "ui.teach.open_clipboard");
    assert.equal(teachForCommand("panel.show_inspector", NOT_TAUGHT), null);
    assert.equal(teachForCommand("panel.show_markers", TAUGHT), null);
    assert.equal(teachForCommand("panel.show_markers", null), "ui.teach.open_markers");
  });
});

describe("teachForDeadDigit", () => {
  const press = (extra = {}) => ({
    code: "Digit3",
    mod: false,
    alt: false,
    shift: false,
    repeat: false,
    typing: false,
    modal: false,
    context: "timeline",
    ...extra,
  });

  test("a bare dead digit on the timeline or a letter panel teaches", () => {
    for (const context of ["timeline", "side", "transcript"]) {
      assert.equal(teachForDeadDigit(press({ context }), NOT_TAUGHT), "ui.teach.dead_digit");
    }
  });

  test("not in a number panel: there the digit is already right", () => {
    assert.equal(teachForDeadDigit(press({ context: "markers" }), NOT_TAUGHT), null);
    assert.equal(teachForDeadDigit(press({ context: "clipboard" }), NOT_TAUGHT), null);
  });

  test("not modified, not held, not typing, not behind a dialog", () => {
    assert.equal(teachForDeadDigit(press({ mod: true }), NOT_TAUGHT), null);
    assert.equal(teachForDeadDigit(press({ alt: true }), NOT_TAUGHT), null);
    assert.equal(teachForDeadDigit(press({ shift: true }), NOT_TAUGHT), null);
    assert.equal(teachForDeadDigit(press({ repeat: true }), NOT_TAUGHT), null);
    assert.equal(teachForDeadDigit(press({ typing: true }), NOT_TAUGHT), null);
    assert.equal(teachForDeadDigit(press({ modal: true }), NOT_TAUGHT), null);
    assert.equal(teachForDeadDigit(press({ code: "Digit0" }), NOT_TAUGHT), null);
    assert.equal(teachForDeadDigit(press({ code: "Numpad3" }), NOT_TAUGHT), null);
  });

  test("a learned user is never nagged", () => {
    assert.equal(teachForDeadDigit(press(), TAUGHT), null);
  });
});

function fakeTimers() {
  let pending = null;
  return {
    setTimeout: (fn) => {
      pending = fn;
      return 1;
    },
    clearTimeout: () => {
      pending = null;
    },
    fire: () => {
      const fn = pending;
      pending = null;
      fn?.();
    },
  };
}

describe("createStatusTeacher", () => {
  const parts = () => ({
    menuHint: { textContent: "", hidden: true },
    keyhints: { hidden: false },
    timers: fakeTimers(),
    t: (key) => key,
  });

  test("shows the message over the key hints and restores them when it clears", () => {
    const { menuHint, keyhints, timers, t } = parts();
    const teacher = createStatusTeacher({ menuHint, keyhints, t, timers });
    teacher.show("ui.teach.open_markers");
    assert.equal(menuHint.textContent, "ui.teach.open_markers");
    assert.equal(menuHint.hidden, false);
    assert.equal(keyhints.hidden, true);
    timers.fire();
    assert.equal(menuHint.textContent, "");
    assert.equal(menuHint.hidden, true);
    assert.equal(keyhints.hidden, false);
  });

  test("a menu's own hint is never cleared by the teacher's timer", () => {
    const { menuHint, keyhints, timers, t } = parts();
    const teacher = createStatusTeacher({ menuHint, keyhints, t, timers });
    teacher.show("ui.teach.open_markers");
    // The menu wrote its own hint over the message before the timer fired.
    menuHint.textContent = "menu text";
    timers.fire();
    assert.equal(menuHint.textContent, "menu text");
    assert.equal(menuHint.hidden, false);
    // The teacher touches nothing that is not its own: the menu's own restore cycle
    // brings the key hints back.
    assert.equal(keyhints.hidden, true);
  });

  test("a second show replaces the first and resets the timer", () => {
    const { menuHint, timers, t } = parts();
    const teacher = createStatusTeacher({ menuHint, keyhints: { hidden: false }, t, timers });
    teacher.show("ui.teach.open_markers");
    teacher.show("ui.teach.dead_digit");
    assert.equal(menuHint.textContent, "ui.teach.dead_digit");
    teacher.clear();
    assert.equal(menuHint.textContent, "");
    assert.equal(menuHint.hidden, true);
    // The cancelled timer of the second show cannot resurrect anything.
    timers.fire();
    assert.equal(menuHint.textContent, "");
  });
});

describe("the status-bar hints of the number panels", () => {
  test("Markers and Clipboard lead with their bare-number action", () => {
    const entries = resolveKeymap(DEFAULT_KEYMAP, {}, "mac");
    const registry = createRegistry();
    for (const entry of entries) registry.register(entry.id, () => {});
    for (const [panel, firstId, word] of [
      ["markers", "marker.jump_1", "ui.hint.marker_jump"],
      ["clipboard", "clipboard.play_slot_1", "ui.hint.cart_play"],
    ]) {
      const rows = resolveHints({
        panel,
        hints: STATUS_HINTS,
        entries,
        registry,
        state: {},
        held: {},
        label: (key) => key,
        format: (raw) => raw,
        platform: "mac",
      });
      assert.equal(rows[0].id, firstId);
      assert.equal(rows[0].keys, "1");
      assert.equal(rows[0].label, word);
    }
  });
});

// The cheat sheet carries the teaching line where a user looks for keys; a search is
// after something specific, so the line steps aside then.
import { createCheatSheet } from "../cheatsheet.js";

class El {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.events = {};
    this.attributes = {};
    this.textContent = "";
    this._classes = new Set();
    this.hidden = false;
    this.value = "";
    this.focused = false;
  }
  get classList() {
    const s = this._classes;
    return {
      add: (...cs) =>
        cs.forEach((c) => {
          s.add(c);
        }),
      remove: (...cs) =>
        cs.forEach((c) => {
          s.delete(c);
        }),
      toggle: (c, force) => ((force ?? !s.has(c)) ? s.add(c) : s.delete(c)),
      contains: (c) => s.has(c),
    };
  }
  set className(v) {
    this._classes = new Set(v.split(/\s+/).filter(Boolean));
  }
  setAttribute(k, v) {
    this.attributes[k] = v;
  }
  addEventListener(type, fn) {
    this.events[type] = fn;
  }
  append(...nodes) {
    this.children.push(...nodes);
    for (const n of nodes) n.parent = this;
  }
  replaceChildren(...nodes) {
    this.children = [];
    this.append(...nodes);
  }
  focus() {
    this.focused = true;
  }
  showModal() {
    this.open = true;
  }
  close() {
    this.open = false;
  }
  querySelector() {
    return null;
  }
  querySelectorAll() {
    return [];
  }
  find(pred) {
    if (pred(this)) return this;
    for (const c of this.children) {
      const hit = c.find?.(pred);
      if (hit) return hit;
    }
    return null;
  }
}

globalThis.document = {
  createElement: (tag) => new El(tag),
  body: new El("body"),
};

function makeSheet(getData = () => []) {
  const sheet = createCheatSheet({
    getData,
    t: (key) => key,
    actions: { importKeys() {}, exportKeys() {}, resetKeys() {} },
    getHeld: () => ({}),
  });
  const body = sheet.element.find((c) => c.classList.contains("cheatsheet-body"));
  const search = sheet.element.find((c) => c.classList.contains("cheatsheet-search"));
  return { sheet, body, search };
}

describe("the cheat sheet teaching line", () => {
  test("sits on top of the sheet and steps aside while searching", () => {
    const { sheet, body, search } = makeSheet();
    sheet.open();
    const teach = body.find((c) => c.classList.contains("cheatsheet-teach"));
    assert.equal(teach.textContent, "ui.keys.teach");
    assert.equal(body.children[0], teach);
    search.value = "split";
    search.events.input();
    assert.ok(!body.find((c) => c.classList.contains("cheatsheet-teach")));
    search.value = "";
    search.events.input();
    assert.ok(body.find((c) => c.classList.contains("cheatsheet-teach")));
  });
});
