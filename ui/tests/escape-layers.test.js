// Esc is one transient layer per press, never two things and never destructive (owner,
// 2026-10-22). goHome's order, then each place that used to break the rule.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { filterEscapeAction } from "../clipboard.js";
import { escapeAction, runEscape } from "../escape.js";
import { transcriptEscape } from "../transcript-model.js";

/** The effects of goHome, recorded; `state` is what the layers look at. */
function fakeHome(initial) {
  const state = {
    selection: new Set(),
    rangeTracks: new Set(),
    trackSelection: new Set(),
    ...initial,
  };
  const log = [];
  const fx = {
    blur: () => log.push("blur"),
    discardPreview: () => {
      log.push("discard_preview");
      state.silencePreview = false;
    },
    clearTracks: () => {
      log.push("clear_tracks");
      state.trackSelection = new Set();
      state.rangeMode = "all";
    },
    clearMarks: () => {
      log.push("clear");
      state.selection = new Set();
      state.rangeTracks = new Set();
      state.inPoint = null;
      state.outPoint = null;
    },
    leaveFocus: () => {
      log.push("leave_focus");
      state.focusMode = null;
    },
    focusTimeline: () => log.push("focus_timeline"),
  };
  const press = () => {
    log.length = 0;
    const what = runEscape({ ...state, inTextField: state.inTextField === true }, fx);
    if (what === "blur") state.inTextField = false;
    return [what, [...log]];
  };
  return { state, press };
}

describe("goHome peels one layer per press", () => {
  test("the order: preview, field, track selection, clips and marks, focus mode, home", () => {
    const { press } = fakeHome({
      silencePreview: true,
      inTextField: true,
      trackSelection: new Set(["t"]),
      selection: new Set(["a"]),
      inPoint: 1,
      outPoint: 5,
      focusMode: { ids: ["t"] },
    });
    assert.deepEqual(
      [press(), press(), press(), press(), press(), press(), press()].map(([what]) => what),
      ["discard_preview", "blur", "clear_tracks", "clear", "leave_focus", "home", "home"],
    );
  });

  test("each press does exactly one thing, and always ends with the timeline focused", () => {
    const { press } = fakeHome({
      silencePreview: true,
      inTextField: true,
      trackSelection: new Set(["t"]),
      selection: new Set(["a"]),
      inPoint: 1,
      focusMode: { ids: ["t"] },
    });
    for (let i = 0; i < 6; i += 1) {
      const [what, log] = press();
      assert.deepEqual(
        log,
        what === "home" ? ["focus_timeline"] : [what, "focus_timeline"],
        `press ${i}`,
      );
    }
  });

  test("clearing the clips and marks also puts the focus on the timeline (it did not before)", () => {
    const { press } = fakeHome({ selection: new Set(["a"]) });
    assert.deepEqual(press(), ["clear", ["clear", "focus_timeline"]]);
  });

  test("the Auto-Silence preview goes first, from anywhere, without asking", () => {
    const { press, state } = fakeHome({
      silencePreview: true,
      selection: new Set(["a"]),
      inPoint: 2,
    });
    assert.deepEqual(press(), ["discard_preview", ["discard_preview", "focus_timeline"]]);
    // The selection and the marks are still there; the next Esc continues as usual.
    assert.equal(state.selection.size, 1);
    assert.equal(state.inPoint, 2);
    assert.equal(press()[0], "clear");
  });

  test("a closed preview panel adds no layer", () => {
    assert.equal(escapeAction({ inTextField: false, silencePreview: false }), "home");
  });
});

describe("the transcript's word range", () => {
  const ev = () => ({
    key: "Escape",
    prevented: false,
    stopped: false,
    preventDefault() {
      this.prevented = true;
    },
    stopPropagation() {
      this.stopped = true;
    },
  });

  test("Esc collapses the range to the cursor and stops there, so goHome does not also run", () => {
    const event = ev();
    let set = null;
    const handled = transcriptEscape(event, { cursor: 7, anchor: 3 }, (next) => {
      set = next;
    });
    assert.equal(handled, true);
    assert.deepEqual(set, { cursor: 7, anchor: null });
    assert.equal(event.prevented, true);
    assert.equal(event.stopped, true);
  });

  test("with no range the key is left alone: the next Esc goes the normal way", () => {
    const event = ev();
    let set = null;
    assert.equal(
      transcriptEscape(event, { cursor: 7, anchor: null }, (next) => {
        set = next;
      }),
      false,
    );
    assert.equal(set, null);
    assert.equal(event.stopped, false);
  });

  test("other keys are not its business", () => {
    const event = { ...ev(), key: "ArrowLeft" };
    assert.equal(
      transcriptEscape(event, { cursor: 1, anchor: 0 }, () => {}),
      false,
    );
  });
});

describe("Esc and a running export", () => {
  test("Esc does not cancel an export or an automix; the notice's Cancel button does", () => {
    const source = readFileSync(fileURLToPath(new URL("../app.js", import.meta.url)), "utf8");
    assert.doesNotMatch(source, /key === "Escape" && exportJob/);
    assert.doesNotMatch(source, /Escape[^\n]*cancelExportJob/);
    assert.match(source, /cancelExportJob/); // still wired to the notice's Cancel button
  });
});

describe("the Clipboard filter field", () => {
  test("Esc with text clears the text and stops", () => {
    assert.equal(filterEscapeAction("Escape", "intro"), "clear");
  });
  test("Esc on an empty field falls through to goHome (the focus leaves the field)", () => {
    assert.equal(filterEscapeAction("Escape", ""), "pass");
  });
  test("other keys are typing", () => {
    assert.equal(filterEscapeAction("a", "x"), null);
    assert.equal(filterEscapeAction("Enter", ""), null);
  });
});
