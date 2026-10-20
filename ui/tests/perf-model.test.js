import assert from "node:assert/strict";
import { test } from "node:test";
import { CHECKED, MENU, menuTargets } from "../menu-model.js";
import { DEFAULT_SECONDS, DURATIONS, isRunning, progressOf, reportFolder } from "../perf-model.js";

test("the durations are 10, 30 and 60 seconds, 30 by default", () => {
  assert.deepEqual(DURATIONS, [10, 30, 60]);
  assert.equal(DEFAULT_SECONDS, 30);
});

test("progress is the elapsed share of the span, never past the end", () => {
  assert.equal(progressOf({ state: "running", seconds: 30, elapsed: 15 }).fraction, 0.5);
  assert.equal(progressOf({ state: "running", seconds: 30, elapsed: 99 }).fraction, 1);
  assert.equal(progressOf({ state: "running", seconds: 0, elapsed: 1 }).fraction, 0);
  assert.equal(progressOf({ state: "done", seconds: 30, elapsed: 0 }).fraction, 1);
  assert.equal(progressOf({ state: "idle" }).fraction, 0);
});

test("progress counts whole seconds left", () => {
  assert.equal(progressOf({ state: "running", seconds: 30, elapsed: 12.2 }).left, 18);
  assert.equal(progressOf({ state: "running", seconds: 30, elapsed: 30 }).left, 0);
});

test("only a running recording is running", () => {
  assert.equal(isRunning({ state: "running" }), true);
  for (const state of ["idle", "done", "failed"]) assert.equal(isRunning({ state }), false);
  assert.equal(isRunning(null), false);
});

test("the report folder is the report's path without its file name", () => {
  assert.equal(
    reportFolder("~/Library/Logs/Kuulas/performance-20261020-194503.txt"),
    "~/Library/Logs/Kuulas",
  );
  assert.equal(reportFolder(null), "");
});

test("the log level in force is the checked one, Normal when unknown", () => {
  assert.equal(CHECKED["help.log_debug"]({ logLevel: "DEBUG" }), true);
  assert.equal(CHECKED["help.log_info"]({ logLevel: "DEBUG" }), false);
  assert.equal(CHECKED["help.log_info"]({}), true);
  assert.equal(CHECKED["help.log_warning"]({ logLevel: "WARNING" }), true);
});

test("the Help menu offers the report and the log level", () => {
  const help = MENU.find((top) => top.id === "help");
  const ids = menuTargets([help]);
  for (const id of [
    "help.performance_report",
    "help.log_debug",
    "help.log_info",
    "help.log_warning",
  ]) {
    assert.ok(ids.includes(id), id);
  }
});
