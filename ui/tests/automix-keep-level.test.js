// The "Music level" choice (keep my levels / fit to speech) in the automixer dialog (pure).
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  doneStatus,
  keepChoiceValue,
  keepFromOptions,
  optionEnabled,
  optionsToForm,
  savedOptions,
  validateOptions,
} from "../automix-options-model.js";

const BED = "bed_under_speech_db";
const KEEP = "keep_music_level";
const specs = [
  { key: KEEP, kind: "bool", default: null, group: "music" },
  { key: BED, kind: "number", default: 1, min: -30, max: 6, group: "music" },
];

describe("keep my levels", () => {
  test("unset follows what the automixer can do; a stored choice wins", () => {
    assert.equal(keepFromOptions({}, { keep_music_level: true }), true);
    assert.equal(keepFromOptions({}, { keep_music_level: false }), false);
    assert.equal(keepFromOptions({}, {}), false);
    assert.equal(keepFromOptions({ [KEEP]: false }, { keep_music_level: true }), false);
    assert.equal(keepFromOptions({ [KEEP]: true }, { keep_music_level: true }), true);
    assert.equal(keepFromOptions({ [BED]: -8 }, { keep_music_level: true }), false);
  });

  test("the select's choice is stored only when it differs from the default", () => {
    assert.equal(keepChoiceValue(true, { keep_music_level: true }), null);
    assert.equal(keepChoiceValue(false, { keep_music_level: true }), false);
    assert.equal(keepChoiceValue(false, {}), null);
    assert.equal(keepChoiceValue(true, {}), true);
  });

  test("both choices reach the options; unset does not", () => {
    assert.deepEqual(validateOptions(specs, { [KEEP]: true, [BED]: "1" }).options, {
      [KEEP]: true,
    });
    assert.deepEqual(validateOptions(specs, { [KEEP]: false, [BED]: "-8" }).options, {
      [KEEP]: false,
      [BED]: -8,
    });
    assert.deepEqual(validateOptions(specs, { [KEEP]: null, [BED]: "1" }).options, {});
    assert.equal(optionsToForm(specs, {})[KEEP], null);
  });

  test("the bed level is greyed and never sent while levels are kept", () => {
    const form = { [KEEP]: true, [BED]: "-8" };
    assert.equal(optionEnabled(specs, form, BED), false);
    assert.equal(optionEnabled(specs, { ...form, [KEEP]: false }, BED), true);
    assert.equal(BED in validateOptions(specs, form).options, false);
  });

  test("a bed level that is out of range does not block Mix while kept", () => {
    assert.equal(validateOptions(specs, { [KEEP]: true, [BED]: "99" }).ok, true);
    assert.equal(validateOptions(specs, { [KEEP]: false, [BED]: "99" }).ok, false);
  });

  test("the Kuulas music level is shown as not used while kept", () => {
    const done = { bed_level: { option: BED, offset_db: -10, current: true } };
    const kept = doneStatus(specs, done, { [KEEP]: true, [BED]: "-10" }, [], {});
    assert.equal(kept[BED].state, "unused");
    const fit = doneStatus(specs, done, { [KEEP]: false, [BED]: "-10" }, [], {});
    assert.equal(fit[BED].state, "done");
  });

  test("a choice that is the default anyway is not pinned when saving", () => {
    const form = { [KEEP]: true, [BED]: "1" };
    assert.deepEqual(savedOptions(specs, form, {}, { keep_music_level: true }), {});
    assert.deepEqual(savedOptions(specs, form, {}, { keep_music_level: false }), {
      [KEEP]: true,
    });
    const fit = { ...form, [KEEP]: false };
    assert.deepEqual(savedOptions(specs, fit, {}, { keep_music_level: true }), {
      [KEEP]: false,
    });
  });
});
