// Help topics load lazily, so the first search must trigger the load: whichever
// search field gains focus loads them, then refreshes its results. Devin review
// on #239: the standalone search panel never loaded topics, so a first search
// before opening the Help sidebar found none (owner, 2026-11-19).
import assert from "node:assert/strict";
import { test } from "node:test";
import { loadOnFocus } from "../command-search-ui.js";

const widget = (calls) => {
  const listeners = {};
  return {
    input: {
      addEventListener: (type, fn) => {
        listeners[type] = fn;
      },
    },
    refresh: () => calls.push("refresh"),
    focus: () => listeners.focus?.(),
  };
};

test("focusing the search field loads, then refreshes with the topics in", async () => {
  const calls = [];
  const search = widget(calls);
  loadOnFocus(search, async () => {
    calls.push("load");
  });
  search.focus();
  for (let i = 0; i < 5; i += 1) await Promise.resolve();
  assert.deepEqual(calls, ["load", "refresh"]);
});

test("a failed load still refreshes (the field keeps working on commands alone)", async () => {
  const calls = [];
  const search = widget(calls);
  loadOnFocus(search, async () => {
    calls.push("load");
    throw new Error("offline");
  });
  search.focus();
  for (let i = 0; i < 5; i += 1) await Promise.resolve();
  assert.deepEqual(calls, ["load", "refresh"]);
});

test("both search surfaces wire the loader: the menu field and the panel field", async () => {
  const { readFileSync } = await import("node:fs");
  const source = readFileSync(new URL("../shell-keys.js", import.meta.url), "utf8");
  // menuSearch keeps its loader, and the panel's makeSearch wraps its widget
  // with the same one instead of returning the bare search.
  assert.match(source, /loadOnFocus\(menuSearch/);
  assert.match(
    source,
    /makeSearch: \(hooks\) => \{\s*const widget = makeSearch\(hooks\);\s*loadOnFocus\(widget/,
  );
});
