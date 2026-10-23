import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { arrivedValues, windowChoice } from "../send-window-model.js";

const win = (name) => ({ folder: `/p/${name}.kuulas`, name });

describe("windowChoice: where an entry can go", () => {
  test("no other window: nothing to send to", () => {
    assert.deepEqual(windowChoice([]), { kind: "none" });
    assert.deepEqual(windowChoice(undefined), { kind: "none" });
  });

  test("one other window is the target, no question asked", () => {
    assert.deepEqual(windowChoice([win("Ep 2")]), { kind: "one", target: win("Ep 2") });
  });

  test("several windows: a list to pick from, by name, in the order given", () => {
    const choice = windowChoice([win("Ep 2"), win("Ep 3")]);
    assert.equal(choice.kind, "many");
    assert.deepEqual(
      choice.items.map((item) => [item.id, item.label, item.enabled]),
      [
        ["/p/Ep 2.kuulas", "Ep 2", true],
        ["/p/Ep 3.kuulas", "Ep 3", true],
      ],
    );
  });
});

describe("arrivedValues: what the receiving window says", () => {
  test("names the sender and the entry", () => {
    assert.deepEqual(arrivedValues({ from: "Ep 1", entry: { name: "Intro joke" } }), {
      from: "Ep 1",
      name: "Intro joke",
    });
  });

  test("an entry with no name still gets a word, never 'undefined'", () => {
    assert.deepEqual(arrivedValues({ from: "Ep 1", entry: {} }, "a clip"), {
      from: "Ep 1",
      name: "a clip",
    });
    assert.deepEqual(arrivedValues(null, "a clip"), { from: "", name: "a clip" });
  });
});
