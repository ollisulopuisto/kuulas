import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { assignTarget, CART_SLOTS, cartEntry, cartSlots } from "../cart-model.js";

const e = (id, cart = null) => ({ id, cart });

describe("the cart: numbered clipboard entries", () => {
  test("seven slots: Alt+8 and Alt+9 are the bracket keys of a Finnish Mac", () => {
    assert.equal(CART_SLOTS, 7);
  });

  test("a slot finds the entry that holds it", () => {
    const state = { clipboard: [e("a"), e("b", 2), e("c", 7)] };
    assert.equal(cartEntry(state, 2).id, "b");
    assert.equal(cartEntry(state, 7).id, "c");
    assert.equal(cartEntry(state, 1), null);
    assert.equal(cartEntry({}, 1), null);
  });

  test("the slots in order, empty ones with no entry", () => {
    const slots = cartSlots({ clipboard: [e("a", 3)] });
    assert.deepEqual(
      slots.map((s) => [s.slot, s.entry?.id ?? null]),
      [1, 2, 3, 4, 5, 6, 7].map((n) => [n, n === 3 ? "a" : null]),
    );
  });

  test("assigning goes to the picked entry, else the first (the one shown selected)", () => {
    const state = { clipboard: [e("a"), e("b")], clipboardSelected: "b" };
    assert.equal(assignTarget(state).id, "b");
    assert.equal(assignTarget({ clipboard: [e("a"), e("b")] }).id, "a");
    assert.equal(assignTarget({ clipboard: [] }), null);
  });
});

test("manual cart trim clamps to a small finite range", async () => {
  const { cartTrim } = await import("../cart-model.js");
  assert.equal(cartTrim("2.5"), 2.5);
  assert.equal(cartTrim("bad"), 0);
  assert.equal(cartTrim(50), 12);
  assert.equal(cartTrim(-50), -12);
});

test("rapid cart actions run in order even after a failed request", async () => {
  const { createCartQueue } = await import("../cart-model.js");
  const run = createCartQueue();
  const calls = [];
  let release;
  const waiting = new Promise((resolve) => {
    release = resolve;
  });
  const first = run(async () => {
    calls.push("start");
    await waiting;
    calls.push("logged");
  });
  const second = run(() => {
    calls.push("stop");
    throw new Error("offline");
  });
  const rejected = assert.rejects(second, /offline/);
  const third = run(() => calls.push("next"));
  await Promise.resolve();
  assert.deepEqual(calls, ["start"]);
  release();
  await Promise.all([first, rejected, third]);
  assert.deepEqual(calls, ["start", "logged", "stop", "next"]);
});
