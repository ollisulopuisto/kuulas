import assert from "node:assert/strict";
import { test } from "node:test";
import { findCollisions, resolveKeymap } from "../keymap-config.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { matchesCombo, parseCombo } from "../keys.js";

const entry = (id) => DEFAULT_KEYMAP.find((row) => row.id === id);
test("Mac defaults leave Hide Others and Minimize All to macOS", () => {
  assert.equal(entry("history.part_versions").keys.mac, "Shift+Mod+H");
  assert.deepEqual(entry("clip.mute").keys.mac, ["M"]);
  assert.equal(entry("history.part_versions").keys.other, "Alt+Mod+H");
  assert.deepEqual(entry("clip.mute").keys.other, ["M", "Alt+Mod+M"]);
  assert.deepEqual(findCollisions(resolveKeymap(DEFAULT_KEYMAP, {}, "mac")), []);
});
test("explicit user overrides survive the new defaults", () => {
  const rows = resolveKeymap(
    DEFAULT_KEYMAP,
    { "history.part_versions": "Alt+Mod+H", "clip.mute": ["M", "Alt+Mod+M"] },
    "mac",
  );
  assert.deepEqual(rows.find((r) => r.id === "history.part_versions").raw, ["Alt+Mod+H"]);
  assert.deepEqual(rows.find((r) => r.id === "clip.mute").raw, ["M", "Alt+Mod+M"]);
});

test("exact modifier matching leaves system chords alone", () => {
  const mac = resolveKeymap(DEFAULT_KEYMAP, {}, "mac");
  const fired = (event) =>
    mac
      .filter((r) => r.raw.some((key) => matchesCombo(event, parseCombo(key), "mac")))
      .map((r) => r.id);
  const base = {
    metaKey: true,
    ctrlKey: false,
    altKey: false,
    shiftKey: false,
    getModifierState: () => false,
  };
  assert.deepEqual(fired({ ...base, key: "h", code: "KeyH", altKey: true }), []);
  assert.deepEqual(fired({ ...base, key: "m", code: "KeyM", altKey: true }), []);
  assert.deepEqual(fired({ ...base, key: "H", code: "KeyH", shiftKey: true }), [
    "history.part_versions",
  ]);
  assert.deepEqual(fired({ ...base, metaKey: false, key: "m", code: "KeyM" }), ["clip.mute"]);
});
