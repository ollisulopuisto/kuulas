import assert from "node:assert/strict";
import { test } from "node:test";
import { setupView } from "../orukeet-setup.js";

test("a missing model can be installed or selected", () => {
  const view = setupView({ ready: false, supported: true });
  assert.equal(view.canInstall, true);
  assert.equal(view.canSelect, true);
  assert.equal(view.ready, false);
});

test("installation reports progress and prevents competing changes", () => {
  const view = setupView({ ready: false, supported: true }, { state: "running", progress: 0.5 });
  assert.equal(view.busy, true);
  assert.equal(view.canInstall, false);
  assert.equal(view.canSelect, false);
  assert.equal(view.progress, 0.5);
});

test("failed and cancelled installation can be retried", () => {
  const status = { ready: false, supported: true };
  const failed = setupView(status, { state: "failed", error: { text: "offline" } });
  assert.equal(failed.error, "offline");
  assert.equal(failed.canInstall, true);
  assert.equal(setupView(status, { state: "cancelled" }).cancelled, true);
});

test("a previously usable model remains usable after an install failure", () => {
  const view = setupView({ ready: true, supported: true }, { state: "failed" });
  assert.equal(view.ready, true);
  assert.equal(view.canSelect, true);
});


test("low-memory policy refuses even a previously installed model", () => {
  const view = setupView({ ready: true, supported: true, eligible: false });
  assert.equal(view.ready, false);
  assert.equal(view.canInstall, false);
  assert.equal(view.canSelect, false);
});
