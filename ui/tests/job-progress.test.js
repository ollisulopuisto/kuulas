import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { progressView } from "../job-progress.js";

describe("progressView: what a running job's bar and text show", () => {
  test("a job that knows how far it is gives a bar value and its own message", () => {
    assert.deepEqual(
      progressView(
        { state: "running", progress: 0.4, indeterminate: false, message: "Reading track 2 of 5…" },
        "Measuring…",
      ),
      { value: 0.4, text: "Reading track 2 of 5…", percent: 40 },
    );
  });

  test("an indeterminate or just-queued job has no value, only a text", () => {
    assert.deepEqual(
      progressView(
        { state: "queued", progress: 0, indeterminate: true, message: "" },
        "Measuring…",
      ),
      { value: null, text: "Measuring…", percent: null },
    );
    assert.equal(
      progressView({ state: "running", progress: 0, indeterminate: true, message: "x" }, "f").value,
      null,
    );
  });

  test("a job at zero that is not indeterminate shows an empty bar, not a moving one", () => {
    assert.equal(
      progressView({ state: "running", progress: 0, indeterminate: false, message: "" }, "f").value,
      0,
    );
  });

  test("the value is kept between 0 and 1 and never given for a missing job", () => {
    assert.equal(
      progressView({ state: "running", progress: 3, indeterminate: false, message: "" }, "f").value,
      1,
    );
    assert.deepEqual(progressView(null, "Measuring…"), {
      value: null,
      text: "Measuring…",
      percent: null,
    });
  });

  test("the percent is a whole number, never past 99 while it still runs", () => {
    assert.equal(
      progressView({ state: "running", progress: 0.999, indeterminate: false, message: "" }, "f")
        .percent,
      99,
    );
    assert.equal(
      progressView({ state: "completed", progress: 1, indeterminate: false, message: "" }, "f")
        .percent,
      100,
    );
  });
});
