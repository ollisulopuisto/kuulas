// The three user choices map to the bounded value the automixer understands.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { balanceChoice, balanceValue, unsupportedChanged } from "../automix-options-model.js";

describe("speaker balance choice", () => {
  test("uses the project recommendation for its default choice", () => {
    assert.equal(balanceChoice(6), "automatic");
    assert.equal(balanceChoice(2.5), "fine_tune");
  });

  test("maps all three choices to the automixer cap", () => {
    assert.equal(balanceValue("automatic"), 6);
    assert.equal(balanceValue("fine_tune"), 2.5);
    assert.equal(balanceValue("keep"), 0);
  });

  test("a changed cap is reported when the installed tool lacks the flag", () => {
    const specs = [{ key: "balance_speakers_max_db", kind: "number", default: 6, min: 0, max: 6 }];
    assert.deepEqual(
      unsupportedChanged(
        specs,
        { balance_speakers_max_db: "2.5" },
        { balance_speakers_max_db: false },
      ),
      ["balance_speakers_max_db"],
    );
  });
});

import { requestOptions, savedOptions } from "../automix-options-model.js";

describe("the cap belongs to the run, not to the saved settings", () => {
  const specs = [
    { key: "balance_speakers_max_db", kind: "number", default: 6, min: 0, max: 6 },
    { key: "speech_multiband", kind: "bool", default: false },
  ];
  const form = { balance_speakers_max_db: "2.5", speech_multiband: true };

  test("it is never saved", () => {
    assert.deepEqual(savedOptions(specs, form, {}), { speech_multiband: true });
  });

  test("it is always sent with the run, with the saved options", () => {
    assert.deepEqual(requestOptions(specs, form, {}), {
      balance_speakers_max_db: 2.5,
      speech_multiband: true,
    });
  });
});
