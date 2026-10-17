import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";

describe("the command registry", () => {
  test("registers, runs and reports status", () => {
    const registry = createRegistry();
    const calls = [];
    registry.register("a", (event) => calls.push(["a", event]));
    assert.equal(registry.has("a"), true);
    assert.equal(registry.status("a"), "ready");
    assert.equal(registry.run("a", "ev"), true);
    assert.deepEqual(calls, [["a", "ev"]]);
  });

  test("a planned command is listed, never runs, and is not available", () => {
    const registry = createRegistry();
    registry.planned("p", "q");
    assert.equal(registry.has("p"), true);
    assert.equal(registry.status("p"), "planned");
    assert.equal(registry.run("p"), false);
    assert.equal(registry.can("p", {}), false);
  });

  test("an id nobody registered counts as planned", () => {
    const registry = createRegistry();
    assert.equal(registry.status("nobody"), "planned");
    assert.equal(registry.run("nobody"), false);
  });

  test("planMissing marks only the ids with no command", () => {
    const registry = createRegistry();
    registry.register("a", () => {});
    registry.planMissing(["a", "b"]);
    assert.equal(registry.status("a"), "ready");
    assert.equal(registry.status("b"), "planned");
  });

  test("can(state) defaults to true, is a pure predicate, and a thrower is false", () => {
    const registry = createRegistry();
    registry.register("free", () => {});
    registry.register("undo", () => {}, { can: (s) => s.canUndo });
    registry.register("bad", () => {}, {
      can: () => {
        throw new Error("x");
      },
    });
    assert.equal(registry.can("free", {}), true);
    assert.equal(registry.can("undo", { canUndo: false }), false);
    assert.equal(registry.can("undo", { canUndo: true }), true);
    assert.equal(registry.can("bad", {}), false);
  });

  test("a command that cannot apply does not run", () => {
    const registry = createRegistry();
    let ran = 0;
    registry.register("undo", () => ran++, { can: (s) => s.canUndo });
    assert.equal(registry.run("undo", null, { canUndo: false }), false);
    assert.equal(registry.run("undo", null, { canUndo: true }), true);
    assert.equal(ran, 1);
  });

  test("hintKey is kept", () => {
    const registry = createRegistry();
    registry.register("a", () => {}, { hintKey: "cmd.a.hint" });
    assert.equal(registry.hintKey("a"), "cmd.a.hint");
    assert.equal(registry.hintKey("zzz"), null);
  });
});
