import assert from "node:assert/strict";
import { test } from "node:test";
import {
  DEFAULTS,
  normaliseSettings,
  reductionAtReference,
  validateSettings,
} from "../duck-sidechain-model.js";

test("the last style and sidechain values are remembered with safe defaults", () => {
  assert.deepEqual(normaliseSettings(null), DEFAULTS);
  assert.deepEqual(normaliseSettings({ style: "sidechain", ratio: 4 }), {
    ...DEFAULTS,
    style: "sidechain",
    ratio: 4,
  });
  assert.equal(normaliseSettings({ style: "unknown" }).style, "gaps");
});

test("sidechain fields validate ranges and convert milliseconds for analysis", () => {
  const good = validateSettings({
    ...DEFAULTS,
    style: "sidechain",
    ratio: "8",
    threshold_db: "-30",
    attack_ms: "50",
    release_ms: "300",
  });
  assert.deepEqual(good, {
    ok: true,
    errors: {},
    options: {
      style: "sidechain",
      ratio: 8,
      threshold_db: -30,
      attack_s: 0.05,
      release_s: 0.3,
    },
  });
  assert.equal(validateSettings({ ...DEFAULTS, style: "sidechain", ratio: "0" }).ok, false);
  assert.equal(
    validateSettings({ ...DEFAULTS, style: "sidechain", threshold_db: "-90" }).ok,
    false,
  );
  assert.equal(validateSettings({ ...DEFAULTS, style: "sidechain", attack_ms: "0" }).ok, false);
  assert.equal(validateSettings({ ...DEFAULTS, style: "sidechain", release_ms: "5000" }).ok, false);
});

test("the depth summary reports reduction at the reference speech level", () => {
  assert.equal(reductionAtReference(8, -30, -19), -9.625);
});

test("the gaps style needs no valid sidechain numbers", () => {
  const checked = validateSettings({ ...DEFAULTS, style: "gaps", ratio: "oops", attack_ms: "" });
  assert.equal(checked.ok, true);
  assert.deepEqual(checked.errors, {});
  assert.equal(checked.options.style, "gaps");
  assert.equal(validateSettings({ ...DEFAULTS, style: "sidechain", ratio: "oops" }).ok, false);
});
