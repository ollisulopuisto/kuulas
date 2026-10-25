import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { resolveKeymap } from "../keymap-config.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { createKeymap } from "../keys.js";
import { flashTop } from "../menu-flash.js";

const menus = [
  { items: [{ kind: "item", id: "a" }] },
  { items: [{ kind: "separator" }, { kind: "submenu", items: [{ kind: "item", id: "b" }] }] },
];
const chord = { metaKey: true, ctrlKey: false, altKey: false };
const plain = { metaKey: false, ctrlKey: false, altKey: false };

describe("flashTop: which menu title to flash when a command is run by key", () => {
  test("the menu that holds the command, in a submenu too", () => {
    assert.equal(flashTop(menus, "a", chord), 0);
    assert.equal(flashTop(menus, "b", chord), 1);
  });

  test("Cmd, Ctrl and Alt chords flash; plain keys (Space, J, K, arrows) never do", () => {
    assert.equal(flashTop(menus, "a", { ...plain, ctrlKey: true }), 0);
    assert.equal(flashTop(menus, "a", { ...plain, altKey: true }), 0);
    assert.equal(flashTop(menus, "a", plain), null);
  });

  test("a command in no menu has nothing to flash", () => {
    assert.equal(flashTop(menus, "nowhere", chord), null);
  });
});

describe("the keymap tells which command a key ran", () => {
  const press = (over) => ({
    key: "",
    code: "",
    shiftKey: false,
    altKey: false,
    ctrlKey: false,
    metaKey: false,
    repeat: false,
    target: { tagName: "DIV" },
    preventDefault() {},
    ...over,
  });

  test("onRun hears the id and the event after the command ran", () => {
    const registry = createRegistry();
    const heard = [];
    for (const entry of DEFAULT_KEYMAP) registry.register(entry.id, () => heard.push("ran"));
    const keymap = createKeymap({
      platform: "mac",
      registry,
      getContext: () => "timeline",
      onRun: (id, event) => heard.push([id, event.metaKey]),
    });
    keymap.setEntries(resolveKeymap(DEFAULT_KEYMAP, {}, "mac"));
    keymap.handle(press({ key: "z", code: "KeyZ", metaKey: true }));
    assert.deepEqual(heard, ["ran", ["edit.undo", true]]);
  });
});
