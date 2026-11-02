// Esc and Enter in modal dialogs: the key decision, the stack (topmost only) and an inventory that
// every modal in ui/ uses the helper (or is on a reasoned allow-list).
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { describe, test } from "node:test";
import {
  dialogKeyAction,
  enhanceDialog,
  fieldKind,
  handleDialogKey,
  openDialogs,
  primaryOf,
  topDialog,
} from "../dialog-keys.js";

const key = (k, extra = {}) => ({ key: k, ...extra });
const ctx = (extra = {}) => ({
  field: "none",
  dirty: false,
  hasPrimary: true,
  safeDefault: false,
  ...extra,
});

describe("dialogKeyAction", () => {
  test("Esc cancels", () => assert.equal(dialogKeyAction(key("Escape"), ctx()), "cancel"));
  test("Esc in a typed-in text field only leaves the field", () => {
    assert.equal(dialogKeyAction(key("Escape"), ctx({ field: "text", dirty: true })), "blur");
    assert.equal(dialogKeyAction(key("Escape"), ctx({ field: "text", dirty: false })), "cancel");
    assert.equal(dialogKeyAction(key("Escape"), ctx({ field: "textarea", dirty: true })), "blur");
  });
  test("IME composition and handled keys do nothing", () => {
    assert.equal(dialogKeyAction(key("Escape", { isComposing: true }), ctx()), "none");
    assert.equal(dialogKeyAction(key("Enter", { keyCode: 229 }), ctx()), "none");
    assert.equal(dialogKeyAction(key("Enter", { defaultPrevented: true }), ctx()), "none");
  });
  test("Esc with a modifier is not ours", () => {
    assert.equal(dialogKeyAction(key("Escape", { metaKey: true }), ctx()), "none");
    assert.equal(dialogKeyAction(key("Escape", { shiftKey: true }), ctx()), "none");
  });
  test("Enter accepts, also from a text field", () => {
    assert.equal(dialogKeyAction(key("Enter"), ctx()), "accept");
    assert.equal(dialogKeyAction(key("Enter"), ctx({ field: "text" })), "accept");
  });
  test("Enter is left alone in a textarea, on a button and in a select", () => {
    for (const field of ["textarea", "button", "select"]) {
      assert.equal(dialogKeyAction(key("Enter"), ctx({ field })), "none", field);
    }
  });
  test("Mod+Enter accepts from anywhere", () => {
    for (const field of ["textarea", "button", "select", "text"]) {
      assert.equal(dialogKeyAction(key("Enter", { metaKey: true }), ctx({ field })), "accept");
      assert.equal(dialogKeyAction(key("Enter", { ctrlKey: true }), ctx({ field })), "accept");
    }
  });
  test("Shift+Enter and Alt+Enter are reserved", () => {
    assert.equal(dialogKeyAction(key("Enter", { shiftKey: true }), ctx()), "none");
    assert.equal(dialogKeyAction(key("Enter", { altKey: true }), ctx()), "none");
  });
  test("no usable primary: Enter does nothing", () => {
    assert.equal(dialogKeyAction(key("Enter"), ctx({ hasPrimary: false })), "none");
  });
  test("safe default: Enter cancels, Mod+Enter does not accept", () => {
    const safe = ctx({ safeDefault: true });
    assert.equal(dialogKeyAction(key("Enter"), safe), "cancel");
    assert.equal(dialogKeyAction(key("Enter", { metaKey: true }), safe), "none");
    assert.equal(dialogKeyAction(key("Enter"), { ...safe, field: "button" }), "none");
    assert.equal(dialogKeyAction(key("Escape"), safe), "cancel");
  });
  test("other keys are not ours", () => assert.equal(dialogKeyAction(key("a"), ctx()), "none"));
});

describe("an open suggestion list", () => {
  const open = {
    tagName: "INPUT",
    type: "text",
    getAttribute: (n) => (n === "aria-expanded" ? "true" : null),
  };
  const closed = { ...open, getAttribute: () => "false" };
  test("an expanded combobox owns Esc and Enter (the list handles them)", () => {
    assert.equal(fieldKind(open), "popup");
    assert.equal(fieldKind(closed), "text");
    assert.equal(dialogKeyAction(key("Escape"), ctx({ field: "popup", dirty: true })), "none");
    assert.equal(dialogKeyAction(key("Enter"), ctx({ field: "popup" })), "none");
    assert.equal(
      dialogKeyAction(key("Enter", { metaKey: true }), ctx({ field: "popup" })),
      "accept",
    );
  });
});

describe("fieldKind", () => {
  test("classifies the focused control", () => {
    assert.equal(fieldKind({ tagName: "TEXTAREA" }), "textarea");
    assert.equal(fieldKind({ tagName: "SELECT" }), "select");
    assert.equal(fieldKind({ tagName: "BUTTON" }), "button");
    assert.equal(fieldKind({ tagName: "INPUT", type: "text" }), "text");
    assert.equal(fieldKind({ tagName: "INPUT", type: "checkbox" }), "none");
    assert.equal(fieldKind({ tagName: "INPUT", type: "submit" }), "button");
    assert.equal(fieldKind({ tagName: "DIV" }), "none");
    assert.equal(fieldKind(null), "none");
  });
});

// A dialog stand-in: just what the helper touches.
function fakeDialog(name, { primaries = ["go"], cancels = ["no"], onCancel = null } = {}) {
  const listeners = {};
  const mk = (id) => ({
    id,
    dataset: {},
    disabled: false,
    hidden: false,
    clicked: 0,
    click() {
      this.clicked++;
    },
  });
  const buttons = { primary: primaries.map(mk), cancel: cancels.map(mk) };
  const d = {
    name,
    open: false,
    buttons,
    showModal() {
      d.open = true;
    },
    close() {
      d.open = false;
      for (const f of listeners.close ?? []) f();
    },
    addEventListener(type, fn) {
      listeners[type] = [...(listeners[type] ?? []), fn];
    },
    dispatchEvent(event) {
      for (const f of listeners[event.type] ?? []) f(event);
      if (onCancel && event.type === "cancel") onCancel(event);
      return !event.defaultPrevented;
    },
    querySelectorAll(sel) {
      if (sel === "[data-dialog-primary]") return buttons.primary;
      if (sel === "[data-dialog-cancel]") return buttons.cancel;
      return [];
    },
    querySelector() {
      return null;
    },
  };
  enhanceDialog(d, { t: (k) => k });
  return d;
}
const press = (k, extra = {}) => {
  const e = {
    key: k,
    target: { tagName: "BODY" },
    prevented: false,
    preventDefault() {
      this.prevented = true;
    },
    stopPropagation() {},
    ...extra,
  };
  return { e, action: handleDialogKey(e, e.target) };
};

describe("data-dialog-enter-local", () => {
  test("Enter in a marked field does nothing (the record view's transcript search)", () => {
    const d = fakeDialog("rec");
    d.showModal();
    const local = {
      tagName: "INPUT",
      closest: (sel) => (sel === "[data-dialog-enter-local]" ? {} : null),
    };
    const { e, action } = press("Enter", { target: local });
    assert.equal(action, "none");
    assert.equal(e.prevented, false);
    assert.equal(d.open, true);
    d.close();
  });
  test("Enter elsewhere still presses the primary", () => {
    const d = fakeDialog("rec2");
    d.showModal();
    const { action } = press("Enter");
    assert.equal(action, "accept");
    d.close();
  });
});

describe("the stack", () => {
  test("Esc closes only the topmost dialog, the next Esc the one below", () => {
    const a = fakeDialog("a");
    const b = fakeDialog("b");
    a.showModal();
    b.showModal();
    assert.equal(topDialog(), b);
    press("Escape");
    assert.equal(b.open, false);
    assert.equal(a.open, true);
    assert.deepEqual(openDialogs(), [a]);
    press("Escape");
    assert.equal(a.open, false);
    assert.equal(topDialog(), null);
  });
  test("a dialog that vetoes cancel stays open", () => {
    const d = fakeDialog("rec", { onCancel: (e) => e.preventDefault() });
    d.showModal();
    press("Escape");
    assert.equal(d.open, true);
    d.close();
  });
  test("Enter presses the first shown, enabled primary", () => {
    const d = fakeDialog("s", { primaries: ["start", "send"] });
    d.buttons.primary[0].hidden = true;
    d.showModal();
    const { action, e } = press("Enter");
    assert.equal(action, "accept");
    assert.equal(e.prevented, true);
    assert.equal(d.buttons.primary[1].clicked, 1);
    assert.equal(primaryOf(d), d.buttons.primary[1]);
    d.buttons.primary[1].disabled = true;
    assert.equal(press("Enter").action, "none");
    d.close();
  });
  test("with no dialog open nothing is handled", () => {
    const { action, e } = press("Escape");
    assert.equal(action, "none");
    assert.equal(e.prevented, false);
  });
  test("hints go on the marked buttons", () => {
    const d = fakeDialog("h");
    assert.equal(d.buttons.cancel[0].dataset.keyHint, "key.escape");
    assert.equal(d.buttons.primary[0].dataset.keyHint, "↵");
  });
});

// -- inventory ------------------------------------------------------------------------------
const uiDir = new URL("../", import.meta.url);
const sources = readdirSync(uiDir).filter((f) => f.endsWith(".js"));
const read = (f) => readFileSync(new URL(f, uiDir), "utf8");

// Files that make a <dialog> must call enhanceDialog once per dialog.
const makesDialog = /(?:createElement|el|make|element)\(\s*"dialog"/g;

// Overlays that are not native modal dialogs, with the reason they keep their own keys.
const ALLOW = {
  "palette.js": "command palette: a combobox panel; Esc closes, Enter runs the highlighted row",
  "command-search-ui.js": "command/key search panel: same combobox keys as the palette",
  "help-panel.js": "docked sidebar panel, not modal; Esc returns to the timeline",
};

describe("inventory", () => {
  test("every <dialog> in ui/ goes through enhanceDialog", () => {
    let count = 0;
    for (const f of sources) {
      const src = read(f);
      const made = (src.match(makesDialog) ?? []).length;
      if (made === 0) continue;
      count += made;
      const enhanced = (src.match(/enhanceDialog\(/g) ?? []).length;
      assert.ok(enhanced >= made, `${f}: ${made} dialog(s), ${enhanced} enhanceDialog call(s)`);
    }
    assert.ok(count >= 13, `found only ${count} dialogs`);
  });
  test("every role=dialog overlay is on the reasoned allow-list", () => {
    for (const f of sources) {
      if (f === "dialog-keys.js") continue;
      const src = read(f);
      if (/setAttribute\("role", "dialog"\)/.test(src)) {
        assert.ok(ALLOW[f], `${f} is a dialog-like overlay: use enhanceDialog or allow-list it`);
      }
    }
    for (const f of Object.keys(ALLOW)) assert.ok(sources.includes(f), `${f} no longer exists`);
    // The one in index.html is non-modal (aria-modal=false): Enter saves, Esc cancels, its own keys.
    assert.match(read("index.html"), /id="placeholder-editor"[^>]*aria-modal="false"/);
  });
  test("the dialog keys are installed once, in app.js", () => {
    assert.match(read("app.js"), /installDialogKeys\(/);
  });
  test("every dialog marks a cancel button", () => {
    for (const f of sources) {
      const src = read(f);
      if ((src.match(makesDialog) ?? []).length === 0) continue;
      assert.match(src, /dataset\.dialogCancel/, `${f}: no dialogCancel mark`);
    }
  });
});
