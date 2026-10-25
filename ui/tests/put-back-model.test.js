import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { canPutBack, commandArgs, describePlan, outcomeKey, placeKey } from "../put-back-model.js";

const RATE = 100;
const plan = {
  site: { kind: "seam", frame: 400, track: null, candidates: [], why: "" },
  at: 400,
  mode: "insert",
  length: 124,
  shift: 124,
  scope: ["a", "b", "m"],
  outcomes: [
    { track: "a", outcome: "restored" },
    { track: "b", outcome: "silence" },
    { track: "m", outcome: "split" },
  ],
  blocked: "",
  start: 10,
  end: 20,
  text: "se oli ihan sattumaa et",
};
const nameOf = (id) => id.toUpperCase();

describe("put back: only cut and unused words can come back", () => {
  test("muted and gated words are on the timeline already", () => {
    assert.equal(canPutBack({ status: "cut" }), true);
    assert.equal(canPutBack({ status: "unused" }), true);
    assert.equal(canPutBack({ status: "muted" }), false);
    assert.equal(canPutBack({ status: "gated" }), false);
  });
});

describe("put back: the preview", () => {
  test("says what, where, how far everything moves and what each track gets", () => {
    const view = describePlan(plan, { rate: RATE, nameOf });
    assert.equal(view.text, "se oli ihan sattumaa et");
    assert.equal(view.seconds, 1.24);
    assert.deepEqual(view.place, { key: "ui.putback.place.seam", frame: 400 });
    assert.deepEqual(view.push, { frame: 400, seconds: 1.24, count: 3 });
    assert.deepEqual(
      view.tracks.map((x) => [x.name, x.key]),
      [
        ["A", "ui.putback.out.restored"],
        ["B", "ui.putback.out.silence"],
        ["M", "ui.putback.out.split"],
      ],
    );
    assert.equal(view.canConfirm, true);
  });
  test("a place that fills a gap moves nothing", () => {
    const view = describePlan(
      { ...plan, mode: "place", shift: 0, site: { ...plan.site, kind: "hole" } },
      { rate: RATE, nameOf },
    );
    assert.equal(view.push, null);
    assert.equal(view.place.key, "ui.putback.place.hole");
  });
  test("an unclear place cannot be confirmed, and lists the choices", () => {
    const view = describePlan(
      {
        ...plan,
        blocked: "ambiguous",
        at: null,
        site: { ...plan.site, kind: "ambiguous", candidates: [400, 500] },
      },
      { rate: RATE, nameOf },
    );
    assert.equal(view.canConfirm, false);
    assert.equal(view.place.key, "ui.putback.place.unclear");
    assert.deepEqual(view.candidates, [400, 500]);
  });
  test("every kind and outcome has a message key", () => {
    for (const kind of ["seam", "edge", "hole", "fill", "ambiguous", "none"])
      assert.match(placeKey(kind), /^ui\.putback\.place\./);
    for (const o of [
      "restored",
      "still_in_edit",
      "silence",
      "cut_differently",
      "split",
      "shifted",
      "empty",
    ])
      assert.equal(outcomeKey(o), `ui.putback.out.${o}`);
    assert.equal(outcomeKey("???"), "ui.putback.out.restored");
  });
});

describe("put back: the command", () => {
  test("sends the previewed stretch and the scope, no place of its own", () => {
    assert.deepEqual(commandArgs("m1", plan, ["a", "b"]), {
      media: "m1",
      start: 10,
      end: 20,
      track_ids: ["a", "b"],
    });
  });
  test("at is sent only when the playhead was chosen", () => {
    assert.deepEqual(commandArgs("m1", plan, ["a"], 777), {
      media: "m1",
      start: 10,
      end: 20,
      track_ids: ["a"],
      at: 777,
    });
  });
});
