// The app's side of the series shelf (docs/design/CLIPBOARD-SHELVES.md), out of app.js so it can
// be tested: loading the shelf, the Series toggle, and adopting through the right route.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { adoptRequest, createSeriesShelf } from "../series-shelf.js";

const t = (key) => key;
const shelf = { link: { id: "s", name: "Show" }, found: true, entries: [{ id: "a" }] };

function setup(api) {
  const patches = [];
  const notices = [];
  const errors = [];
  const series = createSeriesShelf({
    api,
    t,
    setState: (patch) => patches.push(patch),
    notify: (text) => notices.push(text),
    showError: (error) => errors.push(error.message),
  });
  return { series, patches, notices, errors };
}

describe("the series shelf in the app", () => {
  test("load puts the shelf in the state", async () => {
    const h = setup({ getSeriesShelf: async () => shelf });
    await h.series.load();
    assert.deepEqual(h.patches, [{ clipboardSeries: shelf }]);
  });

  test("the toggle adds or removes, keeps the answer and says what happened", async () => {
    const asked = [];
    const h = setup({
      seriesShelfAdd: async (id) => {
        asked.push(["add", id]);
        return shelf;
      },
      seriesShelfRemove: async (id) => {
        asked.push(["remove", id]);
        return { ...shelf, entries: [] };
      },
    });
    await h.series.toggle("a", true);
    await h.series.toggle("a", false);
    assert.deepEqual(asked, [
      ["add", "a"],
      ["remove", "a"],
    ]);
    assert.deepEqual(h.notices, ["ui.clipboard.series_added", "ui.clipboard.series_removed"]);
    assert.deepEqual(h.patches.at(-1), { clipboardSeries: { ...shelf, entries: [] } });
  });

  test("a refused add (already there, no series) is shown, the state is left alone", async () => {
    const h = setup({
      seriesShelfAdd: async () => {
        throw new Error("already");
      },
    });
    await h.series.toggle("a", true);
    assert.deepEqual(h.errors, ["already"]);
    assert.deepEqual(h.patches, []);
  });
});

describe("adopting an entry of another shelf", () => {
  const api = {
    seriesShelfAdopt: async (id) => ({ route: "series", id }),
    adoptClipboardEntry: async (entry, from) => ({ route: "plain", id: entry.id, from }),
  };
  test("a series entry goes through the series (its recordings' paths)", async () => {
    assert.deepEqual(await adoptRequest(api, { id: "m1" }, "", "series"), {
      route: "series",
      id: "m1",
    });
  });
  test("shared and other projects' entries go through the plain adopt", async () => {
    assert.deepEqual(await adoptRequest(api, { id: "x" }, "/p/One.kuulas", "other"), {
      route: "plain",
      id: "x",
      from: "/p/One.kuulas",
    });
    assert.equal((await adoptRequest(api, { id: "x" }, "", "")).route, "plain");
  });
});
