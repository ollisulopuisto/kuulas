import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  hasHandMutes,
  methodAvailable,
  normaliseSilence,
  parseNumber,
  previewLines,
  SHOW_METHOD_SELECTOR,
  SILENCE_DEFAULTS,
  SILENCE_METHODS,
  validateSilence,
} from "../silence-model.js";
import { recordOf, restoreFrom } from "../view-memory.js";

describe("Auto-Silence options", () => {
  test("the defaults are the old hard-coded values", () => {
    assert.deepEqual(SILENCE_DEFAULTS, {
      margin_db: 12,
      dominance_db: 6,
      min_open_s: 0.4,
      min_closed_s: 0.3,
      open_before_s: 0.15,
      open_after_s: 0.4,
      method: "threshold",
    });
  });
  test("numbers are read with a comma or a point; junk is null", () => {
    assert.equal(parseNumber("0,4"), 0.4);
    assert.equal(parseNumber(" 7 "), 7);
    assert.equal(parseNumber(""), null);
    assert.equal(parseNumber("abc"), null);
    assert.equal(parseNumber("1e3"), null);
    assert.equal(parseNumber(Number.NaN), null);
  });
  test("stored options are clamped and repaired", () => {
    const got = normaliseSilence({ margin_db: 99, min_closed_s: "x", method: "magic" });
    assert.equal(got.margin_db, 20);
    assert.equal(got.min_closed_s, 0.3);
    assert.equal(got.method, "threshold");
    assert.deepEqual(normaliseSilence(null), SILENCE_DEFAULTS);
    assert.deepEqual(normaliseSilence([1]), SILENCE_DEFAULTS);
  });
  test("the form reports each bad field and does not clamp what was typed", () => {
    const form = { ...SILENCE_DEFAULTS, margin_db: "2", min_open_s: "x" };
    const { ok, errors } = validateSilence(form);
    assert.equal(ok, false);
    assert.equal(errors.margin_db, "ui.silence.error_range");
    assert.equal(errors.min_open_s, "ui.silence.error_number");
    assert.equal(validateSilence({ ...SILENCE_DEFAULTS, margin_db: "8" }).options.margin_db, 8);
  });
});

describe("the compensated method", () => {
  const speech = (muted) => ({ kind: "speech", clips: [{ muted }] });
  test("needs a hand-muted clip on a speech track", () => {
    assert.equal(hasHandMutes({ tracks: [speech(false)] }), false);
    assert.equal(hasHandMutes({ tracks: [speech(false), speech(true)] }), true);
    assert.equal(hasHandMutes({ tracks: [{ kind: "music", clips: [{ muted: true }] }] }), false);
    assert.equal(hasHandMutes(null), false);
  });
  test("only the compensated one is refused without them", () => {
    const none = { tracks: [speech(false)] };
    assert.equal(methodAvailable("threshold", none), true);
    assert.equal(methodAvailable("compensated", none), false);
    assert.equal(methodAvailable("compensated", { tracks: [speech(true)] }), true);
  });
});

describe("the preview text", () => {
  test("one line per track", () => {
    const t = (key, p) => `${key} ${p.name} ${p.close} ${p.stretches} ${p.now}`;
    const lines = previewLines(
      { tracks: [{ name: "Anna", close_s: 41.23, stretches: 12, now_s: 9 }] },
      t,
    );
    assert.deepEqual(lines, ["ui.silence.preview_row Anna 41.2 12 9"]);
    assert.deepEqual(previewLines(null, t), []);
  });
});

describe("remembered per project (view memory)", () => {
  test("the options go into the record and come back, checked", () => {
    const record = recordOf({ autoSilence: { ...SILENCE_DEFAULTS, margin_db: 8 } });
    assert.equal(record.autoSilence.margin_db, 8);
    const { patch } = restoreFrom(
      { autoSilence: { margin_db: 500 } },
      { project: { rate: 48000, tracks: [] }, width: 100, totalFrames: 1000 },
    );
    assert.equal(patch.autoSilence.margin_db, 20);
  });
  test("a project that never chose any has none in the record", () => {
    assert.equal("autoSilence" in recordOf({}), false);
  });
});

describe("the method selector", () => {
  test("is hidden: the compensated method is experimental", () => {
    assert.equal(SHOW_METHOD_SELECTOR, false);
    assert.deepEqual(SILENCE_METHODS, ["threshold", "compensated"]);
  });
});
