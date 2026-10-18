import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { resolveHints } from "../hints.js";
import { resolveKeymap } from "../keymap-config.js";
import { DEFAULT_KEYMAP, STATUS_HINTS } from "../keymap-default.js";

const label = (k) => k;
const fmt = (combo) => `<${combo}>`;
function hints(panel, { held = {}, ready = [], overrides = {} } = {}) {
  const registry = createRegistry();
  for (const id of ready) registry.register(id, () => {});
  registry.planMissing(DEFAULT_KEYMAP.map((e) => e.id));
  return resolveHints({
    panel,
    hints: STATUS_HINTS,
    entries: resolveKeymap(DEFAULT_KEYMAP, overrides, "other"),
    registry,
    state: {},
    held: { alt: false, shift: false, mod: false, ...held },
    label,
    format: fmt,
    platform: "other",
  });
}

describe("status-bar hints", () => {
  test("at most three, only for commands that exist, with the user's keys", () => {
    const rows = hints("timeline", {
      ready: ["transport.play", "view.toggle", "panel.next", "nav.home"],
    });
    assert.equal(rows.length, 3);
    assert.deepEqual(
      rows.map((r) => r.id),
      ["transport.play", "view.toggle", "panel.next"],
    );
    assert.equal(rows[0].keys, "<Space>");
  });

  test("a planned command is not hinted until it lands", () => {
    const planned = hints("timeline", { ready: ["transport.play", "panel.next"] });
    assert.equal(
      planned.some((r) => r.id === "edit.split"),
      false,
    );
    const landed = hints("timeline", { ready: ["transport.play", "edit.split", "panel.next"] });
    assert.equal(
      landed.some((r) => r.id === "edit.split"),
      true,
    );
  });

  test("a remapped key shows at once", () => {
    const rows = hints("timeline", {
      ready: ["transport.play"],
      overrides: { "transport.play": "P" },
    });
    assert.equal(rows[0].keys, "<P>");
  });

  test("with Shift held the hints show the shifted commands", () => {
    const rows = hints("timeline", {
      held: { shift: true },
      ready: ["transport.play", "edit.remove", "edit.remove_track", "panel.next", "panel.previous"],
    });
    const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
    assert.ok(byId["edit.remove_track"]);
    assert.equal(byId["edit.remove_track"].alternate, true);
    assert.equal(byId["edit.remove_track"].keys, "<Shift+X>");
  });

  test("an unknown panel has no hints", () => {
    assert.deepEqual(hints("nowhere"), []);
  });
});
