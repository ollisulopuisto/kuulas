// The core-loop onboarding panel (owner's sketch v2, "build it" 2026-11-12): the five
// keys of the editing loop - I, O, Shift+Cmd+Space (rehearse), X, P - shown as rows the
// app ticks when each command really runs (registry.onRun), not on a bare keypress.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { beforeEach, describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  CORE_LOOP,
  complete,
  emptyCoreLoop,
  noteRun,
  readCoreLoop,
  showsOnLaunch,
  triedCount,
  writeCoreLoop,
} from "../core-loop-model.js";
import { comboParts, createCoreLoopPanel } from "../core-loop-panel.js";
import * as i18n from "../i18n.js";

const read = (path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

describe("the five rows", () => {
  test("are In, Out, rehearse, remove, play-before, in action order", () => {
    assert.deepEqual(
      CORE_LOOP.map((row) => row.id),
      ["in", "out", "preview", "cut", "play"],
    );
    assert.deepEqual(
      CORE_LOOP.map((row) => row.command),
      ["mark.in", "mark.out", "transport.rehearse", "edit.remove", "transport.play_before"],
    );
  });
});

describe("noteRun: a row ticks when its command runs", () => {
  test("each command ticks its own row once", () => {
    let state = emptyCoreLoop();
    for (const row of CORE_LOOP) {
      const step = noteRun(state, row.command);
      assert.equal(step.ticked, row.id);
      state = step.state;
    }
    assert.equal(triedCount(state), 5);
    assert.ok(complete(state));
  });

  test("an unrelated command changes nothing, not even the object", () => {
    const state = emptyCoreLoop();
    const step = noteRun(state, "edit.undo");
    assert.equal(step.state, state);
    assert.equal(step.ticked, null);
  });

  test("a row already ticked does not tick again", () => {
    const first = noteRun(emptyCoreLoop(), "mark.in");
    const second = noteRun(first.state, "mark.in");
    assert.equal(second.state, first.state);
    assert.equal(second.ticked, null);
    assert.equal(triedCount(second.state), 1);
  });

  test("the input is never mutated, even frozen", () => {
    const frozen = Object.freeze({ tried: Object.freeze([]), hidden: false });
    const step = noteRun(frozen, "edit.remove");
    assert.deepEqual(frozen.tried, []);
    assert.deepEqual(step.state.tried, ["cut"]);
  });
});

describe("remembering the panel", () => {
  const store = (initial) => {
    const data = new Map(initial === undefined ? [] : [["core.loop", JSON.stringify(initial)]]);
    return {
      getJson: (key, fallback) => (data.has(key) ? JSON.parse(data.get(key)) : fallback),
      setJson: (key, value) => data.set(key, JSON.stringify(value)),
    };
  };

  test("nothing stored is a fresh panel: shown, nothing tried", () => {
    const state = readCoreLoop(store());
    assert.deepEqual(state, { tried: [], hidden: false });
    assert.ok(showsOnLaunch(state));
  });

  test("a round trip keeps tried rows and the hidden flag", () => {
    const prefs = store();
    writeCoreLoop(prefs, { tried: ["in", "play"], hidden: true });
    assert.deepEqual(readCoreLoop(prefs), { tried: ["in", "play"], hidden: true });
  });

  test("junk stored is not a crash and not a tick: unknown ids and duplicates drop out", () => {
    const state = readCoreLoop(store({ tried: ["in", "nope", "in", 3], hidden: "yes" }));
    assert.deepEqual(state, { tried: ["in"], hidden: false });
    assert.equal(triedCount(state), 1);
  });

  test("hidden stays hidden; a finished loop does not reopen on the next launch", () => {
    assert.ok(!showsOnLaunch({ tried: [], hidden: true }));
    assert.ok(!showsOnLaunch({ tried: ["in", "out", "preview", "cut", "play"], hidden: false }));
    assert.ok(showsOnLaunch({ tried: ["in"], hidden: false }));
  });
});

describe("comboParts: one chip per key", () => {
  beforeEach(() => {
    i18n.setCatalogs({
      en: { "key.space": "Space", "key.ctrl": "Ctrl", "key.shift": "Shift", "key.alt": "Alt" },
      fi: {},
    });
    i18n.setLanguageNow("en");
  });

  test("Shift+Mod+Space is three chips, glyph order on a Mac", () => {
    assert.deepEqual(comboParts("Shift+Mod+Space", "mac"), ["⇧", "⌘", "Space"]);
  });

  test("the same combo names the modifiers elsewhere, modifier first as formatCombo does", () => {
    assert.deepEqual(comboParts("Shift+Mod+Space", "other"), ["Ctrl", "Shift", "Space"]);
  });

  test("a plain letter is one chip, uppercased", () => {
    assert.deepEqual(comboParts("I", "mac"), ["I"]);
    assert.deepEqual(comboParts("p", "other"), ["P"]);
  });

  test("no combo is no chips", () => {
    assert.deepEqual(comboParts(null, "mac"), []);
    assert.deepEqual(comboParts("", "mac"), []);
  });

  test("the plus key keeps its chip, alone and with a modifier", () => {
    assert.deepEqual(comboParts("+", "mac"), ["+"]);
    assert.deepEqual(comboParts("Mod++", "mac"), ["⌘", "+"]);
    assert.deepEqual(comboParts("Mod++", "other"), ["Ctrl", "+"]);
  });
});

// A minimal element stub, the same idea as part-versions-dialog.test.js: the panel keeps
// references to the nodes it builds, so no querySelector is needed.
class El {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.attrs = {};
    this.events = {};
    this.hidden = false;
    this.textContent = "";
    const classes = new Set();
    this.classList = {
      add: (...names) => {
        for (const n of names) classes.add(n);
      },
      remove: (...names) => {
        for (const n of names) classes.delete(n);
      },
      contains: (n) => classes.has(n),
      toggle: (n, force) => {
        const on = force ?? !classes.has(n);
        if (on) classes.add(n);
        else classes.delete(n);
      },
    };
  }
  set className(value) {
    this.classList.add(...String(value).split(" ").filter(Boolean));
  }
  append(...nodes) {
    this.children.push(...nodes);
  }
  replaceChildren(...nodes) {
    this.children = nodes;
  }
  setAttribute(name, value) {
    this.attrs[name] = String(value);
  }
  addEventListener(name, run) {
    this.events[name] = run;
  }
  click() {
    this.events.click?.();
  }
  find(pred) {
    return this.findAll(pred)[0] ?? null;
  }
  findAll(pred, into = []) {
    for (const child of this.children) {
      if (pred(child)) into.push(child);
      child.findAll?.(pred, into);
    }
    return into;
  }
}

globalThis.document = { createElement: (tag) => new El(tag) };

const t = (key, values) => (values ? `${key} ${JSON.stringify(values)}` : key);

function makePanel({ keys = {}, undoCombo = "Mod+Z" } = {}) {
  const root = new El("section");
  root.hidden = true; // the index.html section starts hidden
  const calls = { hidden: 0 };
  const panel = createCoreLoopPanel({
    root,
    t,
    platform: "mac",
    keyOf: (id) => keys[id] ?? null,
    undoCombo,
    onHide: () => {
      calls.hidden += 1;
    },
  });
  return { panel, root, calls };
}

describe("the panel", () => {
  test("renders the title, the intro and five rows with the user's keys", () => {
    const { root } = makePanel({
      keys: { "mark.in": "I", "mark.out": "O", "transport.rehearse": "Shift+Mod+Space" },
    });
    const rows = root.findAll((c) => c.classList.contains("cl-row"));
    assert.equal(rows.length, 5);
    assert.deepEqual(
      rows.map((r) => r.dataset.row),
      ["in", "out", "preview", "cut", "play"],
    );
    const rehearse = rows[2];
    const chips = rehearse.find((c) => c.classList.contains("cl-keys")).children;
    assert.deepEqual(
      chips.map((k) => k.textContent),
      ["⇧", "⌘", "Space"],
    );
    assert.ok(root.find((c) => c.tagName === "H2"));
  });

  test("a remapped key shows as remapped", () => {
    const { root } = makePanel({ keys: { "edit.remove": "Alt+X" } });
    const cut = root.find((c) => c.dataset.row === "cut");
    const chips = cut.find((c) => c.classList.contains("cl-keys")).children;
    assert.deepEqual(
      chips.map((k) => k.textContent),
      ["⌥", "X"],
    );
  });

  test("update marks tried rows done and counts the progress", () => {
    const { panel, root } = makePanel();
    panel.update({ tried: ["in", "cut"], hidden: false });
    const rows = root.findAll((c) => c.classList.contains("cl-row"));
    assert.ok(rows[0].classList.contains("done"));
    assert.ok(!rows[1].classList.contains("done"));
    assert.ok(rows[3].classList.contains("done"));
    const progress = root.find((c) => c.classList.contains("cl-progress"));
    assert.match(progress.textContent, /"tried":2/);
    assert.match(progress.textContent, /"total":5/);
  });

  test("flash marks the row that just ticked", () => {
    const { panel, root } = makePanel();
    panel.flash("preview");
    const row = root.find((c) => c.dataset.row === "preview");
    assert.ok(row.classList.contains("flash"));
  });

  test("show and hide toggle the section; Hide tips reports back once per click", () => {
    const { panel, root, calls } = makePanel();
    assert.ok(root.hidden);
    panel.show();
    assert.ok(!root.hidden);
    const button = root.find((c) => c.tagName === "BUTTON");
    button.click();
    assert.equal(calls.hidden, 1);
    panel.hide();
    assert.ok(root.hidden);
  });

  test("the undo key in the cut row's hint comes from the keymap, not a hardcoded Cmd+Z", () => {
    const { root } = makePanel({ undoCombo: "Mod+Shift+Z" });
    const cut = root.find((c) => c.dataset.row === "cut");
    const hint = cut.find((c) => c.classList.contains("cl-hint"));
    assert.match(hint.textContent, /"undo":"⇧⌘Z"/);
  });
});

describe("the mount point and styles", () => {
  test("index.html mounts the panel in the timeline stack, hidden at first", () => {
    const html = read("../index.html");
    assert.match(html, /<section id="core-loop"[^>]*hidden>/);
    assert.ok(html.indexOf('id="timeline-stack"') < html.indexOf('id="core-loop"'));
    assert.ok(html.indexOf('id="core-loop"') < html.indexOf('id="panel-transcript"'));
  });

  test("style.css styles the rows, the done tick and the flash", () => {
    const css = read("../style.css");
    for (const cls of [".core-loop", ".cl-row", ".cl-dot", ".cl-keys", ".cl-progress"])
      assert.ok(css.includes(cls), cls);
    assert.match(css, /\.cl-row\.done \.cl-dot/);
    assert.match(css, /\.cl-row\.flash/);
  });
});
