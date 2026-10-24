import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { chipText, copiesToastText, createNoticeHold, toastStaysOpen } from "../notice-hold.js";

const note = (text, kind = "ok") => ({ text, kind, options: {} });

describe("createNoticeHold: closing a toast keeps the next ones quiet", () => {
  test("nothing is held until the user closes a toast", () => {
    const hold = createNoticeHold();
    assert.equal(hold.offer(note("a")), true);
    assert.equal(hold.offer(note("b")), true);
    assert.equal(hold.pending(), false);
  });

  test("after the close, a new message is held, not shown, and remembered", () => {
    const hold = createNoticeHold();
    hold.hold();
    assert.equal(hold.offer(note("Colab 53 %")), false);
    assert.equal(hold.offer(note("Colab 75 %")), false);
    assert.equal(hold.pending(), true);
    assert.equal(hold.latest().text, "Colab 75 %");
  });

  test("holding with nothing new is not pending (no dot on the button)", () => {
    const hold = createNoticeHold();
    hold.hold();
    assert.equal(hold.pending(), false);
    assert.equal(hold.latest(), null);
  });

  test("opening it hands back the latest message and ends the hold", () => {
    const hold = createNoticeHold();
    hold.hold();
    hold.offer(note("one"));
    hold.offer(note("two", "error"));
    assert.deepEqual(hold.release(), note("two", "error"));
    assert.equal(hold.pending(), false);
    assert.equal(hold.offer(note("three")), true);
  });

  test("releasing with nothing held hands back nothing", () => {
    const hold = createNoticeHold();
    hold.hold();
    assert.equal(hold.release(), null);
  });

  test("a hold lasts until it is released", () => {
    const hold = createNoticeHold();
    hold.hold();
    for (let i = 0; i < 5; i += 1) assert.equal(hold.offer(note(`m${i}`)), false);
    assert.equal(hold.held, true);
  });
});

describe("chipText: the latest message on the status button, short", () => {
  test("a short message is shown whole", () => {
    assert.equal(chipText("Colab 75 %"), "Colab 75 %");
  });

  test("a long one is cut with an ellipsis, on one line", () => {
    const text = chipText(`Colab litteroi… 75 %: ${"sana ".repeat(40)}`, 40);
    assert.ok(text.length <= 40);
    assert.ok(text.endsWith("…"));
    assert.ok(!text.includes("\n"));
  });

  test("line breaks and runs of spaces collapse", () => {
    assert.equal(chipText("a\n\n  b"), "a b");
  });
});

describe("toastStaysOpen: a toast you are reading or copying does not vanish", () => {
  test("the pointer on it, or text selected in it, keeps it open", () => {
    assert.equal(toastStaysOpen({ hovered: true, selected: false }), true);
    assert.equal(toastStaysOpen({ hovered: false, selected: true }), true);
  });
  test("otherwise its time is up", () => {
    assert.equal(toastStaysOpen({ hovered: false, selected: false }), false);
  });
});

describe("copiesToastText: Cmd+C with the toast's text selected copies the text", () => {
  const inside = { contains: (node) => node === "in" };
  const picked = { isCollapsed: false, anchorNode: "in" };
  test("selected inside the toast", () => {
    assert.equal(copiesToastText({ key: "c", mod: true, selection: picked, notice: inside }), true);
  });
  test("not without Cmd, not another key, not outside, not a collapsed caret", () => {
    const base = { key: "c", mod: true, selection: picked, notice: inside };
    assert.equal(copiesToastText({ ...base, mod: false }), false);
    assert.equal(copiesToastText({ ...base, key: "v" }), false);
    assert.equal(
      copiesToastText({ ...base, selection: { isCollapsed: false, anchorNode: "out" } }),
      false,
    );
    assert.equal(
      copiesToastText({ ...base, selection: { isCollapsed: true, anchorNode: "in" } }),
      false,
    );
  });
});
