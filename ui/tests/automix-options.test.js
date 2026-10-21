// The automixer's switches in the dialog: the pure form model (specs come from the server).
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  changedItems,
  DONE_IN_KUULAS,
  groupSpecs,
  initialOpen,
  optionEnabled,
  optionsToForm,
  prefillOptions,
  requestOptions,
  summaryText,
  unsupportedChanged,
  validateOptions,
} from "../automix-options-model.js";

describe("capability gating", () => {
  const sp = [
    { key: "bed_under_speech_db", kind: "number", default: 1, min: -30, max: 6, group: "music" },
    { key: "n", kind: "number", default: 0.5, min: 0, max: 1, group: "music" },
  ];

  test("a changed option the tool lacks is reported", () => {
    const form = optionsToForm(sp, { bed_under_speech_db: -10 });
    assert.deepEqual(unsupportedChanged(sp, form, { bed_under_speech_db: false }), [
      "bed_under_speech_db",
    ]);
  });

  test("supported, unknown capability, or value at the default: nothing to warn about", () => {
    const form = optionsToForm(sp, { bed_under_speech_db: -10 });
    assert.deepEqual(unsupportedChanged(sp, form, { bed_under_speech_db: true }), []);
    assert.deepEqual(unsupportedChanged(sp, form, {}), []);
    assert.deepEqual(unsupportedChanged(sp, form, undefined), []);
    assert.deepEqual(
      unsupportedChanged(sp, optionsToForm(sp, {}), { bed_under_speech_db: false }),
      [],
    );
  });

  test("the bed level shows 1 by default, accepts the range edges and refuses outside", () => {
    assert.equal(optionsToForm(sp, {}).bed_under_speech_db, "1");
    assert.deepEqual(validateOptions(sp, { bed_under_speech_db: "-30", n: "" }).options, {
      bed_under_speech_db: -30,
    });
    assert.deepEqual(validateOptions(sp, { bed_under_speech_db: "6", n: "" }).options, {
      bed_under_speech_db: 6,
    });
    for (const bad of ["-31", "6.5", "abc", "Infinity"]) {
      assert.equal(validateOptions(sp, { bed_under_speech_db: bad, n: "" }).ok, false, bad);
    }
    assert.deepEqual(validateOptions(sp, { bed_under_speech_db: "1", n: "" }).options, {});
  });
});

test("music ducking uses the Done in Kuulas stage switch", () => {
  assert.equal(DONE_IN_KUULAS.music_duck, "music_duck");
  const specs = [{ key: "music_duck", kind: "bool", default: true, group: "music" }];
  const filled = prefillOptions(specs, { music_duck: { value: false, current: true } }, {});
  assert.deepEqual(filled.options, { music_duck: false });
  const status = { music_duck: { state: "done", offset: false } };
  assert.deepEqual(requestOptions(specs, filled.options, status), { music_duck: false });
});

describe("group summaries", () => {
  const sp = [
    { key: "a", kind: "bool", default: true, group: "g1" },
    { key: "b", kind: "bool", default: false, group: "g1" },
    { key: "n", kind: "number", default: 0.5, min: 0, max: 1, group: "g2" },
    { key: "w", kind: "list", default: null, group: "g2" },
  ];
  const words = { label: (s) => s.key.toUpperCase(), on: "on", off: "off" };

  test("changed items per group: only differences, with a readable value", () => {
    const form = { a: false, b: false, n: "0.7", w: "x y" };
    const changed = changedItems(sp, form, words);
    assert.deepEqual(changed.g1, ["A off"]);
    assert.deepEqual(changed.g2, ["N 0.7", "W x, y"]);
  });

  test("nothing changed gives no entries", () => {
    assert.deepEqual(changedItems(sp, optionsToForm(sp, {}), words), {});
  });

  test("summary text: the names only while collapsed, truncated", () => {
    assert.equal(summaryText([], true, 30), "");
    assert.equal(summaryText(["A off"], true, 30), "A off");
    assert.equal(summaryText(["A off"], false, 30), "");
    assert.equal(
      summaryText(["Debleed off", "Rider off", "More"], true, 20),
      "Debleed off, Rider …",
    );
  });

  test("a group opens by itself when it holds a changed value; remembered state wins", () => {
    assert.equal(initialOpen(true, undefined), true);
    assert.equal(initialOpen(false, undefined), false);
    assert.equal(initialOpen(false, true), true);
    assert.equal(initialOpen(true, false), false);
  });
});

const specs = [
  { key: "minimal", kind: "bool", default: false, group: "minimal" },
  { key: "speech_hp", kind: "bool", default: true, group: "speech", minimal: true },
  { key: "speech_multiband", kind: "bool", default: false, group: "speech" },
  { key: "speech_desmack", kind: "bool", default: true, group: "speech", minimal: true },
  {
    key: "speech_desmack_sensitivity",
    kind: "number",
    default: 0.5,
    group: "speech",
    min: 0,
    max: 1,
    parent: "speech_desmack",
  },
  { key: "speech_mic_duck", kind: "bool", default: false, group: "micduck", minimal: true },
  {
    key: "mic_duck_db",
    kind: "number",
    default: null,
    group: "micduck",
    min: -60,
    max: 0,
    parent: "speech_mic_duck",
  },
  { key: "speech_plugins", kind: "list", default: null, group: "plugins" },
  { key: "plugin_params", kind: "text", default: null, group: "plugins" },
];

describe("optionsToForm", () => {
  test("nothing stored shows the tool's defaults", () => {
    const form = optionsToForm(specs, {});
    assert.equal(form.speech_hp, true);
    assert.equal(form.speech_mic_duck, false);
    assert.equal(form.speech_desmack_sensitivity, "0.5");
    assert.equal(form.mic_duck_db, "");
    assert.equal(form.speech_plugins, "");
  });

  test("stored values replace them; lists become words", () => {
    const form = optionsToForm(specs, {
      speech_hp: false,
      mic_duck_db: -12,
      speech_plugins: ["/a b/x.vst3", "/c.vst3"],
      plugin_params: "x: y=1",
    });
    assert.equal(form.speech_hp, false);
    assert.equal(form.mic_duck_db, "-12");
    assert.equal(form.speech_plugins, '"/a b/x.vst3" /c.vst3');
    assert.equal(form.plugin_params, "x: y=1");
  });

  test("bad stored values are ignored", () => {
    const form = optionsToForm(specs, { speech_hp: "no", nonsense: 1 });
    assert.equal(form.speech_hp, true);
    assert.equal("nonsense" in form, false);
  });
});

describe("validateOptions", () => {
  test("the defaults send nothing", () => {
    assert.deepEqual(validateOptions(specs, optionsToForm(specs, {})), {
      ok: true,
      errors: {},
      options: {},
    });
  });

  test("only what differs is sent, numbers as numbers", () => {
    const form = {
      ...optionsToForm(specs, {}),
      speech_hp: false,
      speech_mic_duck: true,
      mic_duck_db: "-12,5",
      speech_desmack_sensitivity: "0.5",
      speech_plugins: '"/a b/x.vst3" /c.vst3',
      plugin_params: "  x: y=1 ",
    };
    assert.deepEqual(validateOptions(specs, form).options, {
      speech_hp: false,
      speech_mic_duck: true,
      mic_duck_db: -12.5,
      speech_plugins: ["/a b/x.vst3", "/c.vst3"],
      plugin_params: "x: y=1",
    });
  });

  test("bad numbers are named per field", () => {
    for (const bad of ["x", "2", "-0.1", "Infinity", "NaN", "1e999", "0.5.5"]) {
      const form = { ...optionsToForm(specs, {}), speech_desmack_sensitivity: bad };
      const result = validateOptions(specs, form);
      assert.equal(result.ok, false, bad);
      assert.equal(result.errors.speech_desmack_sensitivity, "ui.automix.bad_option_number");
    }
  });

  test("a switch-shaped text is refused", () => {
    const form = { ...optionsToForm(specs, {}), plugin_params: "--evil" };
    assert.equal(validateOptions(specs, form).errors.plugin_params, "ui.automix.bad_option_text");
    const list = { ...optionsToForm(specs, {}), speech_plugins: "/a --b" };
    assert.equal(validateOptions(specs, list).errors.speech_plugins, "ui.automix.bad_option_text");
  });

  test("minimal drops the switches it overrides and their numbers", () => {
    const form = {
      ...optionsToForm(specs, {}),
      minimal: true,
      speech_hp: false,
      speech_mic_duck: true,
      speech_desmack_sensitivity: "0.9",
      speech_multiband: true,
    };
    assert.deepEqual(validateOptions(specs, form).options, {
      minimal: true,
      speech_multiband: true,
    });
  });

  test("a hidden number of an off stage is not checked or sent", () => {
    const form = {
      ...optionsToForm(specs, {}),
      speech_desmack: false,
      speech_desmack_sensitivity: "oops",
    };
    const result = validateOptions(specs, form);
    assert.equal(result.ok, true);
    assert.deepEqual(result.options, { speech_desmack: false });
  });
});

describe("optionEnabled", () => {
  test("minimal greys the stages it overrides, not the others", () => {
    const form = { ...optionsToForm(specs, {}), minimal: true };
    assert.equal(optionEnabled(specs, form, "speech_hp"), false);
    assert.equal(optionEnabled(specs, form, "speech_multiband"), true);
    assert.equal(optionEnabled(specs, form, "plugin_params"), true);
    assert.equal(optionEnabled(specs, form, "minimal"), true);
  });

  test("a number follows its stage", () => {
    const form = optionsToForm(specs, {});
    assert.equal(optionEnabled(specs, form, "mic_duck_db"), false);
    assert.equal(optionEnabled(specs, { ...form, speech_mic_duck: true }, "mic_duck_db"), true);
    assert.equal(optionEnabled(specs, form, "speech_desmack_sensitivity"), true);
    assert.equal(
      optionEnabled(specs, { ...form, speech_desmack: false }, "speech_desmack_sensitivity"),
      false,
    );
  });
});

describe("groupSpecs", () => {
  test("keeps the order and the group of first appearance", () => {
    assert.deepEqual(
      groupSpecs(specs).map((g) => [g.id, g.specs.length]),
      [
        ["minimal", 1],
        ["speech", 4],
        ["micduck", 2],
        ["plugins", 2],
      ],
    );
  });
});
