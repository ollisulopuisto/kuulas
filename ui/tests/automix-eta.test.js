// The automix toast says how long is left (job.eta from the server), built in a pure function.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { automixNotice } from "../automix-model.js";

const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;
const running = { state: "running", progress: 0.49, message: "track 2/4", eta: ["minutes", 12] };

describe("automixNotice time left", () => {
  test("appends the time left to the running text", () => {
    const { text } = automixNotice(running, t);
    assert.ok(text.startsWith("ui.automix.running_percent"), text);
    assert.ok(text.endsWith(' · ui.eta.minutes{"n":12}'), text);
  });

  test("leaves the text as it was without a usable estimate", () => {
    const plain = automixNotice({ ...running, eta: null }, t).text;
    assert.ok(!plain.includes("ui.eta"));
    assert.equal(automixNotice({ ...running, eta: undefined }, t).text, plain);
    assert.equal(automixNotice({ ...running, eta: ["bad", 1] }, t).text, plain);
  });

  test("hours and minutes pass both numbers", () => {
    const { text } = automixNotice({ ...running, eta: ["hours_minutes", [2, 5]] }, t);
    assert.ok(text.endsWith('ui.eta.hours_minutes{"h":2,"m":5}'), text);
  });

  test("under a minute has no number", () => {
    const { text } = automixNotice({ ...running, eta: ["under_minute", 0] }, t);
    assert.ok(text.endsWith("ui.eta.under_minute{}"), text);
  });

  test("not below 5 percent, not for finished or failed jobs", () => {
    assert.ok(!automixNotice({ ...running, progress: 0.04 }, t).text.includes("ui.eta"));
    const done = { state: "completed", eta: ["minutes", 3], result: { path: "/x" } };
    assert.ok(!automixNotice(done, t).text.includes("ui.eta"));
    const failed = { state: "failed", eta: ["minutes", 3], error: { text: "boom" } };
    assert.ok(!automixNotice(failed, t).text.includes("ui.eta"));
  });

  test("an indeterminate job shows no estimate", () => {
    const text = automixNotice({ ...running, indeterminate: true }, t).text;
    assert.ok(!text.includes("ui.eta"));
  });
});
