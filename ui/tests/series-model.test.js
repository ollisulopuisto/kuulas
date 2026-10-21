// Series (docs/design/SERIES.md): the pure parts of the page: the status-bar chip, the words
// for what differs, the next episode's name and folder, the request bodies.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  episodeDefaults,
  newEpisodeRequest,
  nextEpisodeName,
  seriesChip,
  seriesSaveRequest,
} from "../series-model.js";

const t = (key, values) => (values ? `${key} ${JSON.stringify(values)}` : key);

test("no chip without a series", () => {
  assert.equal(seriesChip({ project: { tracks: [] } }, t), null);
  assert.equal(seriesChip({}, t), null);
});

test("the chip names the series and says when the episode differs", () => {
  const project = { series: { id: "s1", name: "Vikasietotila" } };
  const same = seriesChip({ project, series: { found: true, differs: [] } }, t);
  assert.equal(same.differs, false);
  assert.match(same.text, /ui\.series\.chip .*Vikasietotila/);
  const other = seriesChip(
    { project, series: { found: true, differs: ["layout", "auto_silence"] } },
    t,
  );
  assert.equal(other.differs, true);
  assert.match(other.text, /ui\.series\.chip_differs/);
  assert.match(other.title, /ui\.series\.section\.layout/);
  assert.match(other.title, /ui\.series\.section\.auto_silence/);
  const lost = seriesChip({ project, series: { found: false, differs: [] } }, t);
  assert.match(lost.title, /ui\.series\.missing/);
});

test("next episode bumps the last number and keeps its padding", () => {
  assert.equal(nextEpisodeName("Vikasietotila 07"), "Vikasietotila 08");
  assert.equal(nextEpisodeName("Ep 99 final"), "Ep 100 final");
  assert.equal(nextEpisodeName("Pilot"), "Pilot 2");
  assert.equal(nextEpisodeName(""), "");
});

test("episode defaults come from the open project's path", () => {
  assert.deepEqual(episodeDefaults("/Users/o/Shows/Vikasietotila 07.kuulas"), {
    parent: "/Users/o/Shows",
    name: "Vikasietotila 08",
  });
  assert.deepEqual(episodeDefaults(""), { parent: "", name: "" });
});

test("a new episode needs a series, a name and an absolute folder", () => {
  assert.deepEqual(newEpisodeRequest({ parent: "/x", name: "Ep 2", seriesId: "" }), {
    ok: false,
    field: "series",
    key: "ui.series.need_series",
  });
  assert.equal(newEpisodeRequest({ parent: "x", name: "Ep 2", seriesId: "s" }).field, "parent");
  assert.equal(newEpisodeRequest({ parent: "/x", name: " ", seriesId: "s" }).field, "name");
  assert.deepEqual(newEpisodeRequest({ parent: " /x ", name: "Ep 2", seriesId: "s" }), {
    ok: true,
    body: { parent: "/x", name: "Ep 2", series_id: "s" },
  });
});

test("saving a new series needs a name; a linked project needs none", () => {
  assert.equal(seriesSaveRequest({ linked: false, name: "  ", autoSilence: {} }).ok, false);
  assert.deepEqual(seriesSaveRequest({ linked: false, name: " Show ", autoSilence: { a: 1 } }), {
    ok: true,
    body: { name: "Show", auto_silence: { a: 1 } },
  });
  assert.deepEqual(seriesSaveRequest({ linked: true, name: "", autoSilence: null }), {
    ok: true,
    body: {},
  });
  assert.deepEqual(seriesSaveRequest({ linked: false, seriesId: "s1", autoSilence: null }), {
    ok: true,
    body: { series_id: "s1" },
  });
});
