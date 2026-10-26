import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { MENU, menuTargets } from "../menu-model.js";
import {
  applyToolbarMenu,
  DEFAULT_LAYOUT,
  dropIndex,
  moveButton,
  normalizeLayout,
  pinButton,
  resetLayout,
  stepButton,
  toolbarMenuItems,
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

describe("the right-click menu (WP86: pin from any menu row, remove from the rail)", () => {
  const layout = ["a", "b"];

  test("a command that is not on the toolbar offers Add to toolbar", () => {
    assert.deepEqual(toolbarMenuItems("c", layout), [
      { id: "pin", labelKey: "ui.rail.menu.add", enabled: true },
    ]);
  });

  test("a command that is on the toolbar offers Remove from toolbar", () => {
    assert.deepEqual(toolbarMenuItems("a", layout), [
      { id: "unpin", labelKey: "ui.rail.menu.remove", enabled: true },
    ]);
  });

  test("picking Add puts the command at the end, as the user's own act", () => {
    assert.deepEqual(applyToolbarMenu(layout, "c", "pin"), ["a", "b", "c"]);
  });

  test("picking Remove takes it away and the others keep their order", () => {
    assert.deepEqual(applyToolbarMenu(["a", "b", "c"], "b", "unpin"), ["a", "c"]);
  });

  test("anything else changes nothing, not even the object", () => {
    assert.equal(applyToolbarMenu(layout, "a", "other"), layout);
  });
});

describe("dragging a button (WP86: the user is the only one who moves a button)", () => {
  // Three buttons, their vertical centres at 10, 30 and 50.
  const mids = [10, 30, 50];

  test("dropped above the others it goes first", () => {
    assert.equal(dropIndex(mids, 2, 0), 0);
  });

  test("dropped between two others it goes between them", () => {
    assert.equal(dropIndex(mids, 0, 40), 1);
    assert.equal(dropIndex(mids, 2, 20), 1);
  });

  test("dropped below the others it goes last", () => {
    assert.equal(dropIndex(mids, 0, 90), 2);
  });

  test("dropped where it was it stays where it was", () => {
    assert.equal(dropIndex(mids, 1, 30), 1);
    assert.equal(dropIndex(mids, 0, 10), 0);
  });

  test("the index is for the list without the dragged button, as moveButton takes it", () => {
    const layout = ["a", "b", "c"];
    assert.deepEqual(moveButton(layout, "a", dropIndex(mids, 0, 40)), ["b", "a", "c"]);
  });

  test("a step moves one place and stops at the ends", () => {
    const layout = ["a", "b", "c"];
    assert.deepEqual(stepButton(layout, "b", -1), ["b", "a", "c"]);
    assert.deepEqual(stepButton(layout, "b", 1), ["a", "c", "b"]);
    assert.equal(stepButton(layout, "a", -1), layout);
    assert.equal(stepButton(layout, "c", 1), layout);
    assert.equal(stepButton(layout, "x", 1), layout);
  });
});
