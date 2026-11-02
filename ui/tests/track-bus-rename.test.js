import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { renamedName } from "../tracks.js";

const source = readFileSync(new URL("../tracks.js", import.meta.url), "utf8");

describe("inline header rename decision", () => {
  test("a changed, non-empty name commits, trimmed", () => {
    assert.equal(renamedName("  Voices 2 ", "Voices"), "Voices 2");
    assert.equal(renamedName("Uusi väylä", "Bus 1"), "Uusi väylä");
  });
  test("blank or unchanged names commit nothing", () => {
    assert.equal(renamedName("", "Voices"), null);
    assert.equal(renamedName("   ", "Voices"), null);
    assert.equal(renamedName("Voices", "Voices"), null);
  });
});

describe("bus headers rename like track headers", () => {
  test("both names wire double-click to the shared inline rename", () => {
    assert.match(source, /rename\(name, id, "track"\)/);
    assert.match(source, /rename\(name, id, "bus"\)/);
    assert.match(source, /t\("ui\.bus\.rename"\)/);
  });
  test("a bus rename commits set_bus; a track rename keeps set_track", () => {
    assert.match(source, /"set_bus" : "set_track"/);
    assert.match(source, /bus_id: id, name: value/);
    assert.match(source, /track_id: id, name: value/);
    assert.match(source, /patchBus\(p, id, \{ name: value \}\)/);
  });
  test("a rename double-click on the bus name never folds the bus", () => {
    assert.match(source, /event\.stopPropagation\(\);\s*rename\(name, id, "bus"\)/);
  });
});
