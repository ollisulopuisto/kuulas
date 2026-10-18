import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  DEFAULT_PREFS,
  loadImportPrefs,
  PREFS_KEY,
  panelModel,
  saveImportPrefs,
} from "../import-panel.js";

const memory = (initial = {}) => {
  const data = new Map(Object.entries(initial));
  return {
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, String(value)),
    data,
  };
};
const broken = {
  getItem() {
    throw new Error("blocked");
  },
  setItem() {
    throw new Error("blocked");
  },
};

const summary = (imported, failures = [], warnings = []) => ({ imported, failures, warnings });

describe("remembered import choices", () => {
  test("nothing stored: the defaults, which change nothing from today", () => {
    assert.deepEqual(loadImportPrefs(memory()), { order: "given", trackNaming: "file" });
    assert.deepEqual(DEFAULT_PREFS, { order: "given", trackNaming: "file" });
  });

  test("a saved choice comes back", () => {
    const storage = memory();
    saveImportPrefs({ order: "name", trackNaming: "person" }, storage);
    assert.deepEqual(loadImportPrefs(storage), { order: "name", trackNaming: "person" });
  });

  test("garbage in storage falls back field by field", () => {
    const storage = memory({ [PREFS_KEY]: '{"order":"sideways","trackNaming":"person"}' });
    assert.deepEqual(loadImportPrefs(storage), { order: "given", trackNaming: "person" });
    assert.deepEqual(loadImportPrefs(memory({ [PREFS_KEY]: "{nope" })), DEFAULT_PREFS);
  });

  test("blocked storage neither throws nor loses the defaults", () => {
    assert.deepEqual(loadImportPrefs(broken), DEFAULT_PREFS);
    assert.doesNotThrow(() => saveImportPrefs({ order: "time", trackNaming: "file" }, broken));
    assert.deepEqual(loadImportPrefs(undefined), DEFAULT_PREFS);
  });
});

describe("the panel after an import", () => {
  test("four files side by side: the plain sentence, both alternatives offered", () => {
    const model = panelModel(summary(4), { mode: "side_by_side" });
    assert.equal(model.status, "ok");
    assert.equal(model.titleKey, "ui.import.done_sync");
    assert.deepEqual(model.titleParams, { count: 4 });
    assert.equal(model.canSequence, true);
    assert.equal(model.canUndo, true);
    assert.deepEqual(model.failures, []);
  });

  test("one file: nothing to put one after another", () => {
    const model = panelModel(summary(1), { mode: "side_by_side" });
    assert.equal(model.titleKey, "ui.import.done_one");
    assert.equal(model.canSequence, false);
  });

  test("already one after another: no second offer", () => {
    const model = panelModel(summary(3), { mode: "sequential" });
    assert.equal(model.titleKey, "ui.import.done_sequence");
    assert.equal(model.canSequence, false);
  });

  test("a bad file is named with its reason and the rest still counts", () => {
    const model = panelModel(summary(2, [{ name: "bad.wav", text: "damaged" }]), {
      mode: "side_by_side",
    });
    assert.equal(model.status, "partial");
    assert.equal(model.titleParams.count, 2);
    assert.deepEqual(model.failures, [{ name: "bad.wav", text: "damaged" }]);
    assert.equal(model.canUndo, true);
  });

  test("nothing imported: failures only, nothing to undo or redo", () => {
    const model = panelModel(summary(0, [{ name: "a.wav", text: "no" }]), {
      mode: "side_by_side",
    });
    assert.equal(model.status, "failed");
    assert.equal(model.titleKey, "ui.import.done_none");
    assert.equal(model.canUndo, false);
    assert.equal(model.canSequence, false);
  });

  test("warnings are kept, a warning alone is still a success", () => {
    const model = panelModel(summary(2, [], [{ name: "a.wav", text: "converted" }]), {
      mode: "side_by_side",
    });
    assert.equal(model.status, "ok");
    assert.deepEqual(model.warnings, [{ name: "a.wav", text: "converted" }]);
  });

  test("an empty report is a failure with nothing listed", () => {
    const model = panelModel(summary(0), { mode: "side_by_side" });
    assert.equal(model.status, "failed");
    assert.deepEqual(model.failures, []);
  });
});
