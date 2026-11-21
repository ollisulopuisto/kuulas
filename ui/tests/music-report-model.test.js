// File > Music report… (WP25): the pure parts of the dialog. The server builds the report
// (src/kuulas/music_report.py); this file's model only lays it out: the preview rows, the
// summary line, the warnings, the tab-separated copy and the reason an empty report is empty.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  COLUMNS,
  emptyReasonKey,
  previewRows,
  reportQuery,
  selectionLine,
  summaryOf,
  toTsv,
  warningsOf,
} from "../music-report-model.js";

const t = (key, values) => (values ? `${key} ${JSON.stringify(values)}` : key);

const row = (over = {}) => ({
  order: 1,
  title: "Intro",
  artist: "The Band",
  composer: "C. Omposer",
  publisher: "Pub",
  isrc: "FI123",
  file_name: "intro.wav",
  in_time: "00:00:05",
  out_time: "00:00:35",
  duration: "00:00:30",
  background: false,
  missing_metadata: false,
  ...over,
});

test("the preview has the report's columns, with the use spelled out", () => {
  const [a, b] = previewRows([row(), row({ order: 2, background: true })], t);
  assert.deepEqual(
    COLUMNS.map((c) => c.key),
    ["order", "title", "artist", "composer", "publisher", "in_time", "duration", "usage"],
  );
  assert.deepEqual(a.cells, [
    "1",
    "Intro",
    "The Band",
    "C. Omposer",
    "Pub",
    "00:00:05",
    "00:00:30",
    "music_report.featured",
  ]);
  assert.equal(b.cells[7], "music_report.background");
  assert.equal(a.missing, false);
});

test("a piece without a title shows its file name, marked missing", () => {
  const [r] = previewRows([row({ title: "", missing_metadata: true })], t);
  assert.equal(r.cells[1], "intro.wav");
  assert.equal(r.missing, true);
});

test("the summary counts pieces and adds up the music time", () => {
  const s = summaryOf([row(), row({ duration: "00:01:35" }), row({ duration: "01:00:00" })]);
  assert.equal(s.pieces, 3);
  assert.equal(s.seconds, 30 + 95 + 3600);
  assert.equal(s.time, "01:02:05");
  assert.deepEqual(summaryOf([]), { pieces: 0, seconds: 0, time: "00:00:00" });
});

test("warnings say which pieces lack a title or an artist", () => {
  const rows = [
    row(),
    row({ order: 2, title: "", missing_metadata: true }),
    row({ order: 3, artist: "", missing_metadata: true }),
    row({ order: 4, title: "", artist: "", file_name: "x.wav", missing_metadata: true }),
  ];
  assert.deepEqual(warningsOf(rows), [
    { order: 2, label: "intro.wav", missing: ["title"] },
    { order: 3, label: "Intro", missing: ["artist"] },
    { order: 4, label: "x.wav", missing: ["title", "artist"] },
  ]);
  assert.deepEqual(warningsOf([row()]), []);
});

test("Copy as table is tab separated, with a header and the programme times", () => {
  const text = toTsv([row(), row({ order: 2, title: "A\tB\nC" })], t);
  const lines = text.split("\n");
  assert.equal(lines.length, 3);
  assert.equal(
    lines[0],
    [
      "music_report.header.order",
      "music_report.header.title",
      "music_report.header.artist",
      "music_report.header.composer",
      "music_report.header.publisher",
      "music_report.header.isrc",
      "music_report.header.file_name",
      "music_report.header.in",
      "music_report.header.out",
      "music_report.header.duration",
      "music_report.header.usage",
    ].join("\t"),
  );
  assert.deepEqual(lines[1].split("\t"), [
    "1",
    "Intro",
    "The Band",
    "C. Omposer",
    "Pub",
    "FI123",
    "intro.wav",
    "00:00:05",
    "00:00:35",
    "00:00:30",
    "music_report.featured",
  ]);
  // A tab or a line break inside a cell would shift the columns; both become a space.
  assert.equal(lines[2].split("\t")[1], "A B C");
});

test("Copy as table guards cells a spreadsheet would run as a formula", () => {
  const text = toTsv([row({ title: "=SUM(A1)" })], t);
  assert.equal(text.split("\n")[1].split("\t")[1], "'=SUM(A1)");
});

const track = (over = {}) => ({
  id: "m",
  kind: "music",
  mute: false,
  clips: [{ muted: false }],
  ...over,
});

test("an empty report says why: no music track, muted, no clips, or nothing heard", () => {
  assert.equal(
    emptyReasonKey({ tracks: [{ id: "s", kind: "speech", clips: [{}] }] }),
    "ui.music_report.empty_no_tracks",
  );
  assert.equal(emptyReasonKey({ tracks: [track({ mute: true })] }), "ui.music_report.empty_muted");
  assert.equal(
    emptyReasonKey({ tracks: [track({ clips: [] })] }),
    "ui.music_report.empty_no_clips",
  );
  assert.equal(
    emptyReasonKey({ tracks: [track({ clips: [{ muted: true }] })] }),
    "ui.music_report.empty_no_clips",
  );
  // One muted track and one without clips: the muted one is named first.
  assert.equal(
    emptyReasonKey({ tracks: [track({ mute: true }), track({ id: "n", clips: [] })] }),
    "ui.music_report.empty_muted",
  );
  assert.equal(emptyReasonKey({ tracks: [track()] }), "ui.music_report.empty_silent");
  assert.equal(emptyReasonKey(null), "ui.music_report.empty_no_tracks");
});

test("the report's query carries the selection's span in frames, or nothing for the whole edit", () => {
  assert.equal(reportQuery("json", null), "format=json");
  assert.equal(reportQuery("json", [96000, 144000]), "format=json&start=96000&end=144000");
  assert.equal(reportQuery("csv", [0, 48000]), "format=csv&start=0&end=48000");
  assert.equal(reportQuery("csv"), "format=csv");
  // The HTML is a download: the server names the file only when asked to.
  assert.equal(reportQuery("html", [1, 2]), "format=html&download=1&start=1&end=2");
  assert.equal(reportQuery("html", null), "format=html&download=1");
});

test("the selection line names the span, and says tracks do not count", () => {
  const clips = { source: "clips", range: [48000 * 12, 48000 * 18 + 24000], trackIds: ["m"] };
  assert.equal(selectionLine(null, true, 48000, t), "");
  assert.equal(
    selectionLine({ ...clips, trackIds: null }, true, 48000, t),
    'ui.music_report.selection_only {"span":"00.12-00.18"}',
  );
  assert.equal(
    selectionLine(clips, true, 48000, t),
    'ui.music_report.selection_only {"span":"00.12-00.18"} ui.music_report.tracks_ignored',
  );
  assert.equal(
    selectionLine({ ...clips, trackIds: null }, false, 48000, t),
    'ui.music_report.selection_off {"span":"00.12-00.18"}',
  );
});

test("an empty report of a selection says the selection has no music, not that it is silenced", () => {
  assert.equal(emptyReasonKey({ tracks: [track()] }, true), "ui.music_report.empty_selection");
  assert.equal(emptyReasonKey({ tracks: [track()] }, false), "ui.music_report.empty_silent");
  // The edit's own reasons still come first.
  assert.equal(
    emptyReasonKey({ tracks: [track({ mute: true })] }, true),
    "ui.music_report.empty_muted",
  );
  assert.equal(emptyReasonKey(null, true), "ui.music_report.empty_no_tracks");
});

test("copied reports preserve solo warnings even without rows", () => {
  const notice = "Solo is active: some music is excluded from this report.";
  assert.equal(toTsv([], t, [notice]).split("\n").at(-1).split("\t").at(-1), notice);
  assert.equal(toTsv([row()], t, [notice]).split("\n").at(-1).split("\t").at(-1), notice);
});

test("copied warning keeps column headings first and all records rectangular", () => {
  const lines = toTsv([], t, ["Solo warning"])
    .split("\n")
    .map((line) => line.split("\t"));
  assert.equal(lines[0][0], toTsv([], t).split("\t")[0]);
  assert.equal(lines[1].length, lines[0].length);
  assert.equal(lines[1].at(-1), "Solo warning");
  assert.ok(lines[1].slice(0, -1).every((cell) => cell === ""));
});

test("empty reasons respect master solo and muted-bus routing", () => {
  const music = track({ id: "m", bus: "b" });
  for (const project of [
    { tracks: [music, { id: "s", kind: "speech", solo: true }] },
    { tracks: [music], buses: [{ id: "b", mute: true }] },
  ]) {
    assert.equal(emptyReasonKey(project), "ui.music_report.empty_mix_muted");
  }
  assert.equal(
    emptyReasonKey({ tracks: [track({ solo: true, mute: true })] }),
    "ui.music_report.empty_silent",
  );
});

test("copied solo warning has a Metadata header, not a music classification", () => {
  const lines = toTsv([row()], t, ["Solo warning"])
    .split("\n")
    .map((line) => line.split("\t"));
  const metadata = lines[0].indexOf("music_report.header.metadata");
  const use = lines[0].indexOf("music_report.header.usage");
  assert.ok(metadata >= 0);
  assert.equal(lines[1][metadata], "");
  assert.equal(lines[2][metadata], "Solo warning");
  assert.equal(lines[2][use], "");
  assert.ok(lines.every((cells) => cells.length === lines[0].length));
});
