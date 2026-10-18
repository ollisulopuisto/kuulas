import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { beforeEach, describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  canRestore,
  currentStep,
  dayDistance,
  groupRows,
  mergePage,
  moveSelection,
  needsMore,
  redoSteps,
  relativeTime,
  selectionAfterLoad,
  undoNotice,
} from "../history-model.js";
import * as i18n from "../i18n.js";

const locales = fileURLToPath(new URL("../../src/kuulas/locales/", import.meta.url));
const catalog = (lang) => JSON.parse(readFileSync(`${locales}${lang}.json`, "utf8"));
beforeEach(() => {
  i18n.setCatalogs({ en: catalog("en"), fi: catalog("fi") });
  i18n.setLanguageNow("en");
});
const t = (key, values) => i18n.t(key, values);

// 2026-10-18 17:00 UTC = 20.00 Helsinki (summer time ended 25.10., so UTC+3 here).
const NOW = Date.parse("2026-10-18T17:00:00Z");
const node = (id, created, extra = {}) => ({
  id,
  label: `step ${id}`,
  created,
  is_marker: false,
  side: "past",
  is_head: false,
  ...extra,
});

describe("days in Helsinki, not UTC", () => {
  test("a step just after Helsinki midnight is today although UTC says yesterday", () => {
    assert.equal(dayDistance("2026-10-17T21:30:00Z", NOW), 0); // 00.30 on the 18th Helsinki
    assert.equal(dayDistance("2026-10-17T20:59:00Z", NOW), 1); // 23.59 on the 17th
    assert.equal(dayDistance("2026-10-10T12:00:00Z", NOW), 8);
  });
  test("the stored time is UTC and a bare string without a zone is read as UTC", () => {
    assert.equal(dayDistance("2026-10-18 05:00:00", NOW), 0);
  });
});

describe("relative time", () => {
  test("recent, today, yesterday and older, in both languages", () => {
    assert.equal(relativeTime("2026-10-18T16:59:40Z", NOW, t), "just now");
    assert.equal(relativeTime("2026-10-18T16:40:00Z", NOW, t), "20 min ago");
    assert.equal(relativeTime("2026-10-18T10:42:00Z", NOW, t), "13.42");
    assert.equal(relativeTime("2026-10-17T19:14:00Z", NOW, t), "yesterday 22.14");
    assert.equal(relativeTime("2026-10-10T07:05:00Z", NOW, t), "10.10. 10.05");
    i18n.setLanguageNow("fi");
    assert.equal(relativeTime("2026-10-18T16:40:00Z", NOW, t), "20 min sitten");
    assert.equal(relativeTime("2026-10-17T19:14:00Z", NOW, t), "eilen 22.14");
  });
  test("a time in the future is not 'ago'", () => {
    assert.equal(relativeTime("2026-10-18T17:00:30Z", NOW, t), "just now");
  });
});

describe("grouping steps by session marker", () => {
  const nodes = [
    node("6", "2026-10-18T16:30:00Z", { is_head: true, side: "head" }),
    node("5", "2026-10-18T16:00:00Z"),
    node("4", "2026-10-18T16:00:00Z", { is_marker: true, marker: "opened" }),
    node("3", "2026-10-17T19:14:00Z", { is_marker: true, marker: "closed" }),
    node("2", "2026-10-17T19:10:00Z"),
  ];
  test("markers become dividers, steps keep their order", () => {
    const rows = groupRows(nodes, NOW, t);
    assert.deepEqual(
      rows.map((r) => r.kind),
      ["step", "step", "marker", "marker", "step"],
    );
    assert.equal(rows[2].text, "Opened today 19.00");
    assert.equal(rows[3].text, "Closed yesterday 22.14");
  });
  test("the head, the redo side and abandoned branches get their own flags", () => {
    const rows = groupRows(
      [
        node("9", "2026-10-18T16:30:00Z", { side: "redo" }),
        node("8", "2026-10-18T16:20:00Z", { side: "head", is_head: true }),
        node("7", "2026-10-18T16:10:00Z", { side: "branch" }),
        node("6", "2026-10-18T16:00:00Z"),
      ],
      NOW,
      t,
    );
    assert.deepEqual(
      rows.map((r) => [r.dimmed, r.head, r.indent]),
      [
        [true, false, false],
        [false, true, false],
        [true, false, true],
        [false, false, false],
      ],
    );
  });
  test("no markers: a flat list", () => {
    assert.equal(groupRows([node("1", "2026-10-18T16:00:00Z")], NOW, t).length, 1);
  });
  test("the marker's own wording follows the language", () => {
    i18n.setLanguageNow("fi");
    assert.equal(groupRows(nodes, NOW, t)[2].text, "Avattu tänään 19.00");
  });
});

describe("the current step", () => {
  test("a session marker on top of the head makes the step under it current", () => {
    const list = [
      node("6", "2026-10-18T16:00:00Z", {
        is_marker: true,
        marker: "opened",
        is_head: true,
        side: "head",
      }),
      node("5", "2026-10-18T16:00:00Z", { is_marker: true, marker: "closed" }),
      node("4", "2026-10-18T16:00:00Z"),
    ];
    assert.equal(currentStep(list, "6"), "4");
    assert.equal(groupRows(list, NOW, t).find((r) => r.head).id, "4");
    assert.equal(selectionAfterLoad(null, list, "6"), "4");
    assert.equal(currentStep(list, "gone"), null);
  });
  test("restore compares with the current step, not the marker", () => {
    const state = { panel: "history", head: "6", historyCurrent: "4", historySelected: "4" };
    assert.equal(canRestore(state), false);
    assert.equal(canRestore({ ...state, historySelected: "3" }), true);
  });
});

describe("the redo side", () => {
  test("is what Redo would walk, newest first", () => {
    const list = [
      node("9", "2026-10-18T16:30:00Z", { side: "redo" }),
      node("8", "2026-10-18T16:20:00Z", { side: "redo" }),
      node("7", "2026-10-18T16:10:00Z", { side: "head", is_head: true }),
      node("6", "2026-10-18T16:00:00Z", { side: "branch" }),
    ];
    assert.deepEqual(
      redoSteps(list).map((n) => n.id),
      ["9", "8"],
    );
  });
});

describe("paging", () => {
  test("a new page is appended below, a repeated step is not doubled", () => {
    const merged = mergePage([node("5", "x"), node("4", "x")], [node("4", "x"), node("3", "x")]);
    assert.deepEqual(
      merged.map((n) => n.id),
      ["5", "4", "3"],
    );
  });
  test("a fresh first page replaces the old head of the list", () => {
    const merged = mergePage(
      [node("5", "x", { side: "past" })],
      [node("5", "x", { side: "redo" })],
    );
    assert.equal(merged[0].side, "redo");
  });
  test("more is asked for near the bottom, once, and only if there is more", () => {
    const near = { scrollTop: 900, clientHeight: 300, scrollHeight: 1300 };
    assert.equal(needsMore({ ...near, more: true, loading: false }), true);
    assert.equal(needsMore({ ...near, more: true, loading: true }), false);
    assert.equal(needsMore({ ...near, more: false, loading: false }), false);
    assert.equal(
      needsMore({
        scrollTop: 0,
        clientHeight: 300,
        scrollHeight: 4000,
        more: true,
        loading: false,
      }),
      false,
    );
  });
  test("a list too short to scroll still asks for more", () => {
    assert.equal(
      needsMore({ scrollTop: 0, clientHeight: 300, scrollHeight: 200, more: true, loading: false }),
      true,
    );
  });
});

describe("selection", () => {
  const list = [
    node("5", "x", { is_head: true, side: "head" }),
    node("4", "x", { is_marker: true, marker: "closed" }),
    node("3", "x"),
    node("2", "x"),
  ];
  test("after a load the pick stays if it is still a step in the list", () => {
    assert.equal(selectionAfterLoad("3", list, "5"), "3");
  });
  test("else the head, else the newest step", () => {
    assert.equal(selectionAfterLoad("gone", list, "5"), "5");
    assert.equal(selectionAfterLoad(null, list, "4"), "3");
    assert.equal(selectionAfterLoad(null, [], null), null);
  });
  test("a marker is never selected", () => {
    assert.equal(selectionAfterLoad("4", list, "5"), "5");
  });
  test("arrows move over steps and skip markers; they stop at the ends", () => {
    assert.equal(moveSelection(list, "5", 1), "3");
    assert.equal(moveSelection(list, "3", -1), "5");
    assert.equal(moveSelection(list, "2", 1), "2");
    assert.equal(moveSelection(list, "5", -1), "5");
    assert.equal(moveSelection(list, null, 1), "5");
  });
  test("restore needs a pick that is not already the current state", () => {
    assert.equal(canRestore({ panel: "history", head: "5", historySelected: "3" }), true);
    assert.equal(canRestore({ panel: "history", head: "5", historySelected: "5" }), false);
    assert.equal(canRestore({ panel: "history", head: "5", historySelected: null }), false);
    assert.equal(canRestore({ panel: "timeline", head: "5", historySelected: "3" }), false);
  });
});

describe("the undo and redo notice", () => {
  const moved = (extra = {}) => ({
    direction: "undo",
    crossed_marker: true,
    step: { label: "cut at 12:31", created: "2026-10-17T09:31:00Z" },
    ...extra,
  });
  test("crossing a marker says how long ago the step was", () => {
    assert.equal(undoNotice(moved(), NOW, t), "Undid a step from yesterday: cut at 12:31");
    assert.equal(
      undoNotice(moved({ direction: "redo" }), NOW, t),
      "Redid a step from yesterday: cut at 12:31",
    );
    assert.equal(
      undoNotice(moved({ step: { label: "x", created: "2026-10-18T05:00:00Z" } }), NOW, t),
      "Undid a step from earlier today: x",
    );
    assert.equal(
      undoNotice(moved({ step: { label: "x", created: "2026-10-10T05:00:00Z" } }), NOW, t),
      "Undid a step from 10.10.: x",
    );
  });
  test("in Finnish", () => {
    i18n.setLanguageNow("fi");
    assert.equal(undoNotice(moved(), NOW, t), "Kumottiin askel eiliseltä: cut at 12:31");
  });
  test("no marker crossed, nothing moved: no notice", () => {
    assert.equal(undoNotice(moved({ crossed_marker: false }), NOW, t), null);
    assert.equal(undoNotice(null, NOW, t), null);
    assert.equal(undoNotice(undefined, NOW, t), null);
  });
});
