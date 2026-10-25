import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { resolveKeymap } from "../keymap-config.js";
import {
  createModifierTracker,
  heldFromEvent,
  modClick,
  modifierLayers,
  pickLayer,
} from "../modifiers.js";

// Parked keys (lift-cut on Alt+X) are used here only as fixture data; they are not shipped.
const FIXTURE = [
  {
    id: "cut",
    keys: { mac: ["X", "Mod+X"], other: ["X", "Mod+X"] },
    context: "timeline",
    labelKey: "cmd.cut",
  },
  {
    id: "cut_track",
    keys: { mac: "Shift+X", other: "Shift+X" },
    context: "timeline",
    labelKey: "cmd.cut_track",
  },
  { id: "lift", keys: { mac: "Alt+X", other: "Alt+X" }, context: "timeline", labelKey: "cmd.lift" },
  { id: "view", keys: { mac: "Z", other: "Z" }, context: "global", labelKey: "cmd.view" },
  { id: "fit", keys: { mac: "Shift+Z", other: "Shift+Z" }, context: "global", labelKey: "cmd.fit" },
  { id: "back", keys: { mac: "Alt+Z", other: "Alt+Z" }, context: "global", labelKey: "cmd.back" },
  {
    id: "fwd",
    keys: { mac: "Shift+Alt+Z", other: "Shift+Alt+Z" },
    context: "global",
    labelKey: "cmd.fwd",
  },
  { id: "undo", keys: { mac: "Mod+Z", other: "Mod+Z" }, context: "global", labelKey: "cmd.undo" },
  {
    id: "elsewhere",
    keys: { mac: "Shift+B", other: "Shift+B" },
    context: "transcript",
    labelKey: "cmd.e",
  },
  { id: "b", keys: { mac: "B", other: "B" }, context: "timeline", labelKey: "cmd.b" },
];
const entries = (overrides = {}) => resolveKeymap(FIXTURE, overrides, "other");
const ids = (layers, base) =>
  Object.fromEntries((layers.get(base) ?? []).map((l) => [l.modifier, l.entry.id]));

describe("modifier layers", () => {
  test("Shift and Alt versions of a key hang under the plain key", () => {
    const layers = modifierLayers(entries(), "other");
    assert.deepEqual(ids(layers, "cut"), { shift: "cut_track", alt: "lift" });
  });

  test("a layer hangs under every shorter version of its key", () => {
    const layers = modifierLayers(entries(), "other");
    assert.deepEqual(ids(layers, "back"), { shift: "fwd" });
    assert.deepEqual(ids(layers, "view"), { shift: "fit", alt: "back", "alt+shift": "fwd" });
  });

  test("Mod chords are not layers", () => {
    const layers = modifierLayers(entries(), "other");
    assert.equal(Object.values(ids(layers, "view")).includes("undo"), false);
    assert.equal(layers.has("undo"), false);
  });

  test("keys in contexts that never meet are not layers", () => {
    const layers = modifierLayers(entries(), "other");
    assert.deepEqual(ids(layers, "b"), {});
  });

  test("layers follow user overrides", () => {
    const layers = modifierLayers(entries({ cut_track: "Shift+Q", lift: null }), "other");
    assert.deepEqual(ids(layers, "cut"), {});
  });

  test("pickLayer: nothing held is the base, a held set picks its layer", () => {
    const layers = modifierLayers(entries(), "other");
    assert.equal(pickLayer(layers, "cut", { alt: false, shift: false, mod: false }), null);
    assert.equal(pickLayer(layers, "cut", { alt: true, shift: false, mod: false }).id, "lift");
    assert.equal(pickLayer(layers, "view", { alt: true, shift: true, mod: false }).id, "fwd");
    assert.equal(pickLayer(layers, "cut", { alt: true, shift: true, mod: false }), null);
    assert.equal(pickLayer(layers, "cut", { alt: false, shift: true, mod: true }).id, "cut_track");
  });
});

const ev = (over) => ({
  altKey: false,
  shiftKey: false,
  ctrlKey: false,
  metaKey: false,
  getModifierState: () => false,
  ...over,
});

describe("held modifiers", () => {
  test("Option on a Mac, Alt elsewhere, Shift", () => {
    assert.deepEqual(heldFromEvent(ev({ altKey: true }), "mac"), {
      alt: true,
      shift: false,
      mod: false,
    });
    assert.deepEqual(heldFromEvent(ev({ shiftKey: true }), "other"), {
      alt: false,
      shift: true,
      mod: false,
    });
  });

  test("Mod is Cmd on a Mac and Ctrl elsewhere", () => {
    assert.equal(heldFromEvent(ev({ metaKey: true }), "mac").mod, true);
    assert.equal(heldFromEvent(ev({ ctrlKey: true }), "mac").mod, false);
    assert.equal(heldFromEvent(ev({ ctrlKey: true }), "other").mod, true);
    assert.equal(heldFromEvent(ev({ metaKey: true }), "other").mod, false);
  });

  test("AltGr (reported as Ctrl+Alt) holds nothing", () => {
    const altGr = ev({ ctrlKey: true, altKey: true, getModifierState: (k) => k === "AltGraph" });
    assert.deepEqual(heldFromEvent(altGr, "other"), { alt: false, shift: false, mod: false });
  });
});

describe("the modifier tracker", () => {
  test("follows keydown and keyup, and tells listeners only about changes", () => {
    const tracker = createModifierTracker({ platform: "mac" });
    const seen = [];
    tracker.subscribe((held) => seen.push({ ...held }));
    tracker.update(ev({ altKey: true }));
    tracker.update(ev({ altKey: true })); // a repeat: no change
    tracker.update(ev({}));
    assert.deepEqual(
      seen.map((h) => h.alt),
      [true, false],
    );
    assert.equal(tracker.held().alt, false);
  });

  test("blur, a hidden tab and focus loss release everything", () => {
    for (const kind of ["blur", "hidden", "focusloss"]) {
      const tracker = createModifierTracker({ platform: "other" });
      tracker.update(ev({ altKey: true, shiftKey: true }));
      assert.equal(tracker.held().alt, true);
      tracker.reset(kind);
      assert.deepEqual(tracker.held(), { alt: false, shift: false, mod: false });
    }
  });

  test("a later event with no modifier un-sticks a key whose keyup was lost", () => {
    const tracker = createModifierTracker({ platform: "mac" });
    tracker.update(ev({ altKey: true }));
    tracker.update(ev({})); // e.g. a mouse move after the window came back
    assert.equal(tracker.held().alt, false);
  });

  test("AltGr never counts as Alt or Ctrl", () => {
    const tracker = createModifierTracker({ platform: "other" });
    tracker.update(ev({ ctrlKey: true, altKey: true, getModifierState: (k) => k === "AltGraph" }));
    assert.deepEqual(tracker.held(), { alt: false, shift: false, mod: false });
  });
});

describe("modClick: the platform's add-to-selection modifier on a pointer event", () => {
  test("Cmd on a Mac; Ctrl+click is the context menu there, never add", () => {
    assert.equal(modClick(ev({ metaKey: true }), "mac"), true);
    assert.equal(modClick(ev({ ctrlKey: true }), "mac"), false);
  });

  test("Ctrl elsewhere; the Windows key does not count", () => {
    assert.equal(modClick(ev({ ctrlKey: true }), "other"), true);
    assert.equal(modClick(ev({ metaKey: true }), "other"), false);
  });
});
