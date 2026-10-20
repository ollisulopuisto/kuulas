// What Kuulas already did, as the automixer dialog's option model sees it (pure).
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  DONE_IN_KUULAS,
  doneStatus,
  optionsToForm,
  prefillOptions,
  requestOptions,
  savedOptions,
} from "../automix-options-model.js";

describe("done in Kuulas", () => {
  const KEY = "bed_under_speech_db";
  const sp = [{ key: KEY, kind: "number", default: 1, min: -30, max: 6, group: "music" }];
  const entry = (over = {}) => ({
    bed_level: { option: KEY, offset_db: -10, current: true, ...over },
  });

  test("the registry maps option keys to the project's mix_done entries", () => {
    assert.equal(DONE_IN_KUULAS.bed_under_speech_db, "bed_level");
  });

  test("a stored default is replaced by what Kuulas did", () => {
    const got = prefillOptions(sp, entry(), {});
    assert.equal(got.options[KEY], -10);
    assert.deepEqual(got.offered, []);
    assert.equal(optionsToForm(sp, got.options)[KEY], "-10");
  });

  test("a stored value that differs is kept and Kuulas's is offered", () => {
    const got = prefillOptions(sp, entry(), { [KEY]: -6 });
    assert.equal(got.options[KEY], -6);
    assert.deepEqual(got.offered, [KEY]);
  });

  test("a stored value equal to Kuulas's is simply done", () => {
    const got = prefillOptions(sp, entry(), { [KEY]: -10 });
    assert.equal(got.options[KEY], -10);
    assert.deepEqual(got.offered, []);
  });

  test("a stale or absent record changes nothing", () => {
    assert.deepEqual(prefillOptions(sp, entry({ current: false }), {}).options, {});
    assert.deepEqual(prefillOptions(sp, {}, { [KEY]: -6 }).options, { [KEY]: -6 });
    assert.deepEqual(prefillOptions(sp, undefined, {}).offered, []);
  });

  test("the badge shows while the value is Kuulas's and goes when it is edited away", () => {
    const done = entry();
    assert.equal(doneStatus(sp, done, { [KEY]: "-10" }, [], {})[KEY].state, "done");
    assert.equal(doneStatus(sp, done, { [KEY]: "-10,0" }, [], {})[KEY].state, "done");
    assert.equal(doneStatus(sp, done, { [KEY]: "1" }, [], {})[KEY], undefined);
    assert.equal(doneStatus(sp, done, { [KEY]: "-7" }, [], {})[KEY], undefined);
  });

  test("an offered value shows the offer until it is taken", () => {
    const s = doneStatus(sp, entry(), { [KEY]: "-6" }, [KEY], {})[KEY];
    assert.deepEqual([s.state, s.offset], ["offer", -10]);
    assert.equal(doneStatus(sp, entry(), { [KEY]: "-10" }, [KEY], {})[KEY].state, "done");
  });

  test("a stale record gives a hint", () => {
    const s = doneStatus(sp, entry({ current: false }), { [KEY]: "1" }, [], {})[KEY];
    assert.equal(s.state, "stale");
  });

  test("done with an automixer that lacks the switch says so", () => {
    const form = { [KEY]: "-10" };
    assert.equal(doneStatus(sp, entry(), form, [], { [KEY]: false })[KEY].unsupported, true);
    assert.equal(doneStatus(sp, entry(), form, [], { [KEY]: true })[KEY].unsupported, false);
  });

  test("a done value is sent with the run but not saved as the user's setting", () => {
    const form = { [KEY]: "-10" };
    const status = doneStatus(sp, entry(), form, [], {});
    assert.deepEqual(requestOptions(sp, form, status), { [KEY]: -10 });
    assert.deepEqual(savedOptions(sp, form, status), {});
  });

  test("an edited value is saved as usual and nothing extra is sent", () => {
    const form = { [KEY]: "-7" };
    const status = doneStatus(sp, entry(), form, [], {});
    assert.equal(requestOptions(sp, form, status), undefined);
    assert.deepEqual(savedOptions(sp, form, status), { [KEY]: -7 });
  });
});
