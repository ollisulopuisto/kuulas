import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { MENU, menuTargets } from "../menu-model.js";
import {
  DEFAULT_LAYOUT,
  moveButton,
  normalizeLayout,
  pinButton,
  resetLayout,
  unpinButton,
} from "../toolbar-model.js";

describe("the default layout", () => {
  test("is the owner's ten, in workflow order", () => {
    assert.deepEqual(DEFAULT_LAYOUT, [
      "edit.undo",
      "edit.redo",
      "app.import",
      "app.transcribe",
      "app.auto_silence",
      "edit.split",
      "clip.mute",
      "sync.resync_range",
      "export.automix",
      "app.export",
    ]);
  });

  test("names only commands that are in a menu (WP86: every command is in a menu)", () => {
    const inMenu = new Set(menuTargets(MENU));
    for (const id of DEFAULT_LAYOUT) assert.ok(inMenu.has(id), id);
  });
});

describe("a layout changes only when the user changes it", () => {
  const base = ["a", "b", "c"];

  test("a new pin goes to the end, or where it is dropped", () => {
    assert.deepEqual(pinButton(base, "d"), ["a", "b", "c", "d"]);
    assert.deepEqual(pinButton(base, "d", 1), ["a", "d", "b", "c"]);
  });

  test("pinning what is already there changes nothing, not even the object", () => {
    assert.equal(pinButton(base, "b"), base);
  });

  test("removing a button leaves the others in their order", () => {
    assert.deepEqual(unpinButton(base, "b"), ["a", "c"]);
    assert.equal(unpinButton(base, "x"), base);
  });

  test("moving a button puts it at the drop position and keeps the rest in order", () => {
    assert.deepEqual(moveButton(base, "a", 2), ["b", "c", "a"]);
    assert.deepEqual(moveButton(base, "c", 0), ["c", "a", "b"]);
    assert.equal(moveButton(base, "x", 0), base);
  });

  test("reset gives the default order, as a copy", () => {
    const fresh = resetLayout();
    assert.deepEqual(fresh, DEFAULT_LAYOUT);
    assert.notEqual(fresh, DEFAULT_LAYOUT);
  });

  test("the input is never changed", () => {
    const frozen = Object.freeze(["a", "b"]);
    pinButton(frozen, "c");
    unpinButton(frozen, "a");
    moveButton(frozen, "a", 1);
    assert.deepEqual(frozen, ["a", "b"]);
  });
});

describe("normalizeLayout (what was stored)", () => {
  const known = new Set(["a", "b", "c"]);

  test("keeps the stored order of the known commands", () => {
    assert.deepEqual(normalizeLayout(["c", "a"], known), ["c", "a"]);
  });

  test("drops a command that no longer exists and keeps the others where they were", () => {
    assert.deepEqual(normalizeLayout(["a", "gone", "b"], known), ["a", "b"]);
  });

  test("drops repeats and non-strings", () => {
    assert.deepEqual(normalizeLayout(["a", "a", 3, null, "b"], known), ["a", "b"]);
  });

  test("falls back to the default for anything that is not a list", () => {
    assert.deepEqual(normalizeLayout(null, known), DEFAULT_LAYOUT);
    assert.deepEqual(normalizeLayout("a,b", known), DEFAULT_LAYOUT);
    assert.deepEqual(normalizeLayout(undefined, known), DEFAULT_LAYOUT);
  });

  test("an empty stored list is a choice, not a failure: the user removed everything", () => {
    assert.deepEqual(normalizeLayout([], known), []);
  });
});
