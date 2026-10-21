// The History list as drawn (history-model.js historyRows): restores, the steps they rolled
// back, undone and left-behind groups, runs of one setting, and the saved-versions status.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { beforeEach, describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  canGoToRestorePoint,
  canRestore,
  expandAllMap,
  historyRows,
  moveRow,
  restorePointOf,
  visibleNodes,
} from "../history-model.js";
import * as i18n from "../i18n.js";

const locales = fileURLToPath(new URL("../../src/kuulas/locales/", import.meta.url));
const catalog = (lang) => JSON.parse(readFileSync(`${locales}${lang}.json`, "utf8"));
beforeEach(() => {
  i18n.setCatalogs({ en: catalog("en"), fi: catalog("fi") });
  i18n.setLanguageNow("en");
});
const t = (key, values) => i18n.t(key, values);
const NOW = Date.parse("2026-10-18T17:00:00Z");

let clock = 0;
const step = (id, extra = {}) => ({
  id,
  label: `stored ${id}`,
  name: `Step ${id}`,
  name_base: `Step ${id}`,
  name_detail: "",
  run: null,
  created: `2026-10-18T11:${String(10 + (clock++ % 40)).padStart(2, "0")}:00Z`,
  is_marker: false,
  is_head: false,
  side: "past",
  rolled_back_by: null,
  restore_target: null,
  checkpoint: null,
  ...extra,
});

// Newest first, as the server pages: R restored to A, rolling back D, C, B.
const restored = () => [
  step("R", { side: "head", is_head: true, restore_target: "A", name: "Restored to: Step A" }),
  step("D", { side: "rolled_back", rolled_back_by: "R" }),
  step("C", { side: "rolled_back", rolled_back_by: "R" }),
  step("B", { side: "rolled_back", rolled_back_by: "R" }),
  step("A"),
  step("Z"),
];

describe("a restore", () => {
  test("its rolled-back steps are one collapsed group row with a count", () => {
    const rows = historyRows(restored(), NOW, t);
    assert.deepEqual(
      rows.map((r) => [r.kind, r.id]),
      [
        ["step", "R"],
        ["group", "g:rolled_back:D"],
        ["step", "A"],
        ["step", "Z"],
      ],
    );
    const group = rows[1];
    assert.equal(group.group, "rolled_back");
    assert.equal(group.count, 3);
    assert.equal(group.expanded, false);
    assert.equal(group.text, "Rolled back 3 steps");
    assert.equal(group.by, "R");
  });

  test("expanded, the steps follow as dimmed children that say so", () => {
    const rows = historyRows(restored(), NOW, t, { expanded: { "g:rolled_back:D": true } });
    assert.deepEqual(
      rows.map((r) => r.id),
      ["R", "g:rolled_back:D", "D", "C", "B", "A", "Z"],
    );
    const child = rows[2];
    assert.equal(child.dim, "rolled_back");
    assert.equal(child.parent, "g:rolled_back:D");
    assert.equal(child.dimText, "Rolled back");
  });

  test("the restore row is named after its target, the target is the restore point", () => {
    const rows = historyRows(restored(), NOW, t);
    assert.equal(rows[0].label, "Restored to: Step A");
    assert.equal(rows[0].restoreTarget, "A");
    assert.equal(rows[2].restorePoint, true);
    assert.equal(rows[3].restorePoint, false);
  });

  test("an undone restore points at nothing: only the current state's restores do", () => {
    const list = [
      step("R", { side: "redo", restore_target: "A" }),
      step("B", { side: "head", is_head: true }),
      step("A"),
    ];
    const rows = historyRows(list, NOW, t);
    assert.equal(rows.find((r) => r.id === "A").restorePoint, false);
  });

  test("G goes from a restore row to its target", () => {
    const list = restored();
    assert.equal(restorePointOf(list, "R"), "A");
    assert.equal(restorePointOf(list, "A"), null);
    assert.equal(canGoToRestorePoint({ panel: "history", historyRestoreTarget: "A" }), true);
    assert.equal(canGoToRestorePoint({ panel: "timeline", historyRestoreTarget: "A" }), false);
    assert.equal(canGoToRestorePoint({ panel: "history", historyRestoreTarget: null }), false);
  });
});

describe("undone and left-behind steps", () => {
  const list = () => [
    step("E", { side: "redo" }),
    step("D", { side: "redo" }),
    step("C", { side: "head", is_head: true }),
    step("Y", { side: "branch" }),
    step("X", { side: "branch" }),
    step("B"),
  ];
  test("undone is open by default above the head, left behind closed below", () => {
    const rows = historyRows(list(), NOW, t);
    assert.deepEqual(
      rows.map((r) => r.id),
      ["g:undone:E", "E", "D", "C", "g:left_behind:Y", "B"],
    );
    assert.equal(rows[0].text, "Undone · 2 steps (Redo brings them back)");
    assert.equal(rows[0].expanded, true);
    assert.equal(rows[1].dim, "undone");
    assert.equal(rows[4].text, "Left behind · 2 steps");
    assert.equal(rows[4].expanded, false);
  });
  test("the user's choice overrides the default", () => {
    const rows = historyRows(list(), NOW, t, {
      expanded: { "g:undone:E": false, "g:left_behind:Y": true },
    });
    assert.deepEqual(
      rows.map((r) => r.id),
      ["g:undone:E", "C", "g:left_behind:Y", "Y", "X", "B"],
    );
  });
  test("Expand all opens every group, then a second time puts them back", () => {
    const nodes = list();
    const all = expandAllMap(nodes, NOW, t, {});
    assert.deepEqual(historyRows(nodes, NOW, t, { expanded: all }).length, 8);
    assert.deepEqual(expandAllMap(nodes, NOW, t, all), {});
  });
});

describe("runs of one setting on one object", () => {
  const run = (id, detail, extra = {}) =>
    step(id, {
      run: "set_track:t1",
      name_base: "Track settings: Olli",
      name_detail: detail,
      name: `Track settings: Olli · ${detail}`,
      ...extra,
    });
  test("collapse into one row that counts them and shows from where to where", () => {
    const rows = historyRows(
      [run("4", "gain −9.0 dB"), run("3", "gain −6.0 dB"), run("2", "gain −3.0 dB"), step("1")],
      NOW,
      t,
    );
    assert.deepEqual(
      rows.map((r) => r.id),
      ["4", "1"],
    );
    assert.equal(rows[0].label, "Track settings: Olli ×3 · gain −3.0 dB → gain −9.0 dB");
    assert.deepEqual(rows[0].run, { key: "r:4", count: 3, expanded: false });
  });
  test("expanded, the newest keeps its own name and the others follow", () => {
    const rows = historyRows([run("4", "a"), run("3", "b"), step("1")], NOW, t, {
      expanded: { "r:4": true },
    });
    assert.deepEqual(
      rows.map((r) => [r.id, r.label, r.parent ?? null]),
      [
        ["4", "Track settings: Olli · a", null],
        ["3", "Track settings: Olli · b", "r:4"],
        ["1", "Step 1", null],
      ],
    );
  });
  test("the head, a restore point and a saved version split a run", () => {
    const rows = historyRows(
      [
        run("5", "a"),
        run("4", "b", { side: "head", is_head: true }),
        run("3", "c"),
        run("2", "d", { checkpoint: { name: "v1", kind: "manual" } }),
        run("1", "e"),
      ],
      NOW,
      t,
    );
    assert.deepEqual(
      rows.map((r) => r.id),
      ["5", "4", "3", "2", "1"],
    );
  });
});

describe("saved versions only", () => {
  test("each says where it stands, and nothing is grouped", () => {
    const saved = (id, side) => step(id, { side, checkpoint: { name: `v${id}`, kind: "manual" } });
    const rows = historyRows(
      [
        saved("4", "redo"),
        saved("3", "head"),
        saved("2", "rolled_back"),
        saved("1", "branch"),
        saved("0", "past"),
      ],
      NOW,
      t,
      { savedOnly: true },
    );
    assert.deepEqual(
      rows.map((r) => [r.kind, r.stands]),
      [
        ["step", "Undone"],
        ["step", "In the current state"],
        ["step", "Rolled back"],
        ["step", "Left behind"],
        ["step", "In the current state"],
      ],
    );
  });
});

describe("the text filter", () => {
  test("matches the readable name as well as the stored label", () => {
    const nodes = [step("a", { name: "Split: Anna at 1:00.0" }), step("b")];
    assert.deepEqual(
      visibleNodes(nodes, { query: "anna" }).map((n) => n.id),
      ["a"],
    );
    assert.deepEqual(
      visibleNodes(nodes, { query: "stored b" }).map((n) => n.id),
      ["b"],
    );
  });
});

describe("moving and restoring", () => {
  test("the arrows walk the drawn rows, group rows included, markers skipped", () => {
    const rows = historyRows(restored(), NOW, t);
    assert.equal(moveRow(rows, "R", 1), "g:rolled_back:D");
    assert.equal(moveRow(rows, "g:rolled_back:D", 1), "A");
    assert.equal(moveRow(rows, "R", -1), "R");
    assert.equal(moveRow(rows, "hidden", 1), "R");
  });
  test("a group row cannot be restored", () => {
    const state = { panel: "history", historyCurrent: "R", historySelected: "g:rolled_back:D" };
    assert.equal(canRestore(state), false);
  });
});
