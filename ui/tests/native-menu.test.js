import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import {
  createNativeMenuSync,
  isolateMenusForModal,
  MAX_NATIVE_ITEMS,
  nativeMenuSpec,
  runNativeChoice,
  syncWindowMenuHidden,
} from "../native-menu.js";

const item = (id, extra = {}) => ({
  kind: "item",
  id,
  label: id,
  keys: "",
  enabled: true,
  ...extra,
});
const SEP = { kind: "separator" };

describe("nativeMenuSpec", () => {
  test("keeps id, label, keys, enabled and checked, and the arg of a recent project", () => {
    const spec = nativeMenuSpec([
      {
        id: "file",
        label: "Tiedosto",
        items: [
          item("app.save", { label: "Tallenna", keys: "⌘S", enabled: false }),
          item("view.toolbar_labels", { checked: true }),
          item("app.open", { arg: "/p/a.kuulas" }),
        ],
      },
    ]);
    assert.deepEqual(spec, [
      {
        id: "file",
        label: "Tiedosto",
        items: [
          { kind: "item", id: "app.save", label: "Tallenna", keys: "⌘S", enabled: false },
          {
            kind: "item",
            id: "view.toolbar_labels",
            label: "view.toolbar_labels",
            keys: "",
            enabled: true,
            checked: true,
          },
          {
            kind: "item",
            id: "app.open",
            label: "app.open",
            keys: "",
            enabled: true,
            arg: "/p/a.kuulas",
          },
        ],
      },
    ]);
  });

  test("leaves the Help search field out", () => {
    const spec = nativeMenuSpec([
      {
        id: "help",
        label: "Ohje",
        items: [{ ...item("help.search"), kind: "search" }, item("help.keys")],
      },
    ]);
    assert.deepEqual(
      spec[0].items.map((i) => i.id),
      ["help.keys"],
    );
  });

  test("separators never lead, trail or repeat, and an empty submenu goes", () => {
    const spec = nativeMenuSpec([
      {
        id: "a",
        label: "A",
        items: [
          SEP,
          item("one"),
          SEP,
          SEP,
          { kind: "submenu", label: "Empty", items: [SEP] },
          SEP,
          { kind: "submenu", label: "More", items: [item("two"), SEP] },
          SEP,
        ],
      },
    ]);
    assert.deepEqual(
      spec[0].items.map((i) => i.kind),
      ["item", "separator", "submenu"],
    );
    assert.deepEqual(
      spec[0].items[2].items.map((i) => i.id),
      ["two"],
    );
  });

  test("a menu with nothing left is dropped", () => {
    assert.deepEqual(nativeMenuSpec([{ id: "x", label: "X", items: [SEP] }]), []);
  });

  test("the size is capped", () => {
    const many = Array.from({ length: MAX_NATIVE_ITEMS + 50 }, (_, n) => item(`c${n}`));
    const spec = nativeMenuSpec([{ id: "x", label: "X", items: many }]);
    assert.equal(spec[0].items.length, MAX_NATIVE_ITEMS);
  });
});

describe("createNativeMenuSync", () => {
  function setup({ focus = true, api = true } = {}) {
    const sent = [];
    const timers = [];
    const state = { focus, menus: [{ id: "f", label: "F", items: [item("a")] }] };
    const sync = createNativeMenuSync({
      getMenus: () => state.menus,
      getApi: () =>
        api
          ? {
              set_native_menu: (spec) => {
                sent.push(spec);
                return Promise.resolve(true);
              },
            }
          : null,
      hasFocus: () => state.focus,
      setTimer: (fn) => {
        timers.push(fn);
        return timers.length;
      },
      clearTimer: () => {
        timers.length = 0;
      },
    });
    const flush = () => {
      const fns = timers.splice(0);
      for (const fn of fns) fn();
    };
    return { sync, sent, state, flush };
  }

  test("sends once, not again while the menu is unchanged", () => {
    const { sync, sent, flush } = setup();
    sync.push();
    flush();
    sync.push();
    flush();
    assert.equal(sent.length, 1);
  });

  test("sends again when the menu changed, and when forced", () => {
    const { sync, sent, state, flush } = setup();
    sync.push();
    flush();
    state.menus = [{ id: "f", label: "F", items: [item("a", { enabled: false })] }];
    sync.push();
    flush();
    sync.push(true);
    assert.equal(sent.length, 3);
  });

  test("a burst of pushes is one send", () => {
    const { sync, sent, flush } = setup();
    sync.push();
    sync.push();
    sync.push();
    flush();
    assert.equal(sent.length, 1);
  });

  test("a window without focus does not send", () => {
    const { sync, sent, flush } = setup({ focus: false });
    sync.push();
    flush();
    assert.equal(sent.length, 0);
  });

  test("without the wrapper (a browser tab) nothing happens", () => {
    const { sync, sent, flush } = setup({ api: false });
    sync.push();
    flush();
    assert.equal(sent.length, 0);
  });
});

describe("playback keeps notifying (33 ms)", () => {
  function clock() {
    const c = { t: 0, timers: new Map(), id: 0, sent: [] };
    c.setTimer = (fn, ms) => {
      c.id += 1;
      c.timers.set(c.id, { fn, at: c.t + ms });
      return c.id;
    };
    c.clearTimer = (id) => c.timers.delete(id);
    c.advance = (ms) => {
      const end = c.t + ms;
      for (;;) {
        const due = [...c.timers]
          .filter(([, v]) => v.at <= end)
          .sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        c.t = due[1].at;
        c.timers.delete(due[0]);
        due[1].fn();
      }
      c.t = end;
    };
    return c;
  }
  function make(c, menus) {
    return createNativeMenuSync({
      getMenus: () => menus.value,
      getApi: () => ({
        set_native_menu: (spec) => {
          c.sent.push(spec);
          return Promise.resolve(true);
        },
      }),
      setTimer: c.setTimer,
      clearTimer: c.clearTimer,
      now: () => c.t,
    });
  }

  test("a menu change during playback is sent within the max wait", () => {
    const c = clock();
    const menus = { value: [{ id: "f", label: "F", items: [item("a")] }] };
    const sync = make(c, menus);
    sync.push();
    c.advance(33);
    menus.value = [{ id: "f", label: "F", items: [item("a", { enabled: false })] }];
    for (let i = 0; i < 40; i += 1) {
      sync.push();
      c.advance(33);
    }
    assert.ok(c.sent.length >= 1, "the debounce never starved the send");
    assert.equal(c.sent.at(-1)[0].items[0].enabled, false);
  });

  test("taking the bar on focus sends at once, mid-playback", () => {
    const c = clock();
    const menus = { value: [{ id: "f", label: "F", items: [item("a")] }] };
    const sync = make(c, menus);
    for (let i = 0; i < 5; i += 1) {
      sync.push();
      c.advance(33);
    }
    const before = c.sent.length;
    sync.push(true);
    assert.equal(c.sent.length, before + 1);
  });
});

describe("native commands behind a modal", () => {
  const registry = (ran) => ({
    explains: (id) => id.startsWith("edit."),
    run: (id) => ran.push(id),
  });

  test("an editing command is refused while a dialog is open, others and closed dialogs work", () => {
    const ran = [];
    const ctx = (modal) => ({
      registry: registry(ran),
      getState: () => ({}),
      isModal: () => modal,
    });
    assert.equal(runNativeChoice({ id: "edit.cut" }, ctx(true)), false);
    assert.equal(runNativeChoice({ id: "app.preferences" }, ctx(true)), true);
    assert.equal(runNativeChoice({ id: "edit.cut" }, ctx(false)), true);
    assert.deepEqual(ran, ["app.preferences", "edit.cut"]);
  });

  test("the menus switch the editing items off while a dialog is open", () => {
    const menus = [
      {
        id: "e",
        label: "E",
        items: [
          item("edit.cut"),
          { kind: "submenu", label: "S", items: [item("edit.undo")] },
          item("app.save"),
        ],
      },
    ];
    const explains = (id) => id.startsWith("edit.");
    const out = isolateMenusForModal(menus, { explains, isModal: () => true });
    assert.equal(out[0].items[0].enabled, false);
    assert.equal(out[0].items[1].items[0].enabled, false);
    assert.equal(out[0].items[2].enabled, true);
    assert.equal(isolateMenusForModal(menus, { explains, isModal: () => false }), menus);
  });
});

describe("syncWindowMenuHidden", () => {
  function fakeDocument() {
    const attrs = new Set();
    return {
      documentElement: {
        toggleAttribute: (name, force) => (force ? attrs.add(name) : attrs.delete(name)),
        hasAttribute: (name) => attrs.has(name),
      },
    };
  }

  test("hides the window menu only on a confirmed native install", () => {
    // Owner, 2026-11-19: "now that we have the native menu, we don't need to
    // duplicate it inside the app window". Hiding waits for the wrapper's
    // report that the native menus are really drawn, and comes back when the
    // install fails (Devin review on #239: a hidden window menu plus a failed
    // native draw would leave no menus at all).
    const doc = fakeDocument();
    assert.equal(syncWindowMenuHidden(doc, false), false);
    assert.equal(doc.documentElement.hasAttribute("data-native-menu"), false);
    assert.equal(syncWindowMenuHidden(doc, true), true);
    assert.equal(doc.documentElement.hasAttribute("data-native-menu"), true);
    assert.equal(syncWindowMenuHidden(doc, false), false);
    assert.equal(doc.documentElement.hasAttribute("data-native-menu"), false);
  });

  test("the CSS drops the window menu and slims the top bar under the marker", () => {
    const css = readFileSync(new URL("../style.css", import.meta.url), "utf8");
    assert.match(css, /\[data-native-menu\][^{]*#menubar\s*\{[^}]*display:\s*none/);
    const tokens = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");
    assert.match(tokens, /\[data-native-menu\][^{]*\{[^}]*--topbar-h:\s*38px/);
  });

  test("the shell hides the window menu from the wrapper's report", () => {
    const shell = readFileSync(new URL("../shell-keys.js", import.meta.url), "utf8");
    assert.match(shell, /window\.__kuulasNativeMenuResult = \(ok\) => syncWindowMenuHidden\(/);
  });

  test("help search and Show in Menu skip the hidden window menu", () => {
    // Devin review on #239: help.search must not open the Help menu's field
    // under display: none; Show in Menu needs a visible destination instead.
    const shell = readFileSync(new URL("../shell-keys.js", import.meta.url), "utf8");
    assert.match(
      shell,
      /openSearch: \(\) =>[\s\S]*?hasAttribute\("data-native-menu"\)\s*\?\s*searchPanel\.open\(\)/,
    );
    assert.match(
      shell,
      /reveal: \(id\) =>[\s\S]*?hasAttribute\("data-native-menu"\)\s*\?\s*searchPanel\.open\(\)/,
    );
  });
});

describe("createNativeMenuSync install outcome", () => {
  test("a refused push reports not-installed; a queued push stays unconfirmed", () => {
    const installed = [];
    let result = true;
    const sync = createNativeMenuSync({
      getMenus: () => [
        {
          id: "file",
          label: "Tiedosto",
          items: [{ kind: "item", id: "a", label: "A", keys: "", enabled: true }],
        },
      ],
      getApi: () => ({ set_native_menu: () => Promise.resolve(result) }),
      delay: 0,
      onInstall: (ok) => installed.push(ok),
    });
    sync.push(true);
    return new Promise((resolve) => setTimeout(resolve, 10))
      .then(() => {
        assert.deepEqual(installed, []); // queued: the wrapper's report confirms
        result = false;
        sync.push(true);
        return new Promise((r) => setTimeout(r, 10));
      })
      .then(() => {
        assert.deepEqual(installed, [false]); // refused: show the window menu
      });
  });
});
