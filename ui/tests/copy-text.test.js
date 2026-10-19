import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { copyText } from "../copy-text.js";

const blocked = async () => {
  throw new Error("NotAllowedError");
};

describe("copyText", () => {
  it("uses the web clipboard first", async () => {
    const calls = [];
    const ok = await copyText("0:08,938", {
      write: async (text) => calls.push(["web", text]),
      select: () => calls.push(["select"]),
      native: async () => calls.push(["native"]),
    });
    assert.equal(ok, true);
    assert.deepEqual(calls, [["web", "0:08,938"]]);
  });
  it("falls back to the desktop bridge, then to select-and-copy", async () => {
    const calls = [];
    const viaNative = await copyText("1", {
      write: blocked,
      native: async () => calls.push("native"),
      select: () => true,
    });
    assert.equal(viaNative, true);
    assert.deepEqual(calls, ["native"]);
    const viaSelect = await copyText("1", { write: blocked, native: blocked, select: () => true });
    assert.equal(viaSelect, true);
  });
  it("says false when every route fails", async () => {
    assert.equal(
      await copyText("1", { write: blocked, native: blocked, select: () => false }),
      false,
    );
    assert.equal(await copyText("1", {}), false);
  });
});
