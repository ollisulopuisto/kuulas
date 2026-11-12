import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const recordView = readFileSync(new URL("../record-view.js", import.meta.url), "utf8");
test("recording controls sit with the transport, not the menu", () => {
  const menu = html.slice(html.indexOf('<header class="toolbar"'), html.indexOf("</header>"));
  const corner = html.slice(
    html.indexOf('<div class="corner"'),
    html.indexOf("<!-- The toolbar rail"),
  );
  assert.doesNotMatch(menu, /id="rec-chip"/);
  assert.match(corner, /id="play"[\s\S]*id="record"[\s\S]*id="rec-chip"/);
});

test("live transcription can be selected before and during a take", () => {
  assert.match(recordView, /setup\.liveToggle = row/);
  assert.match(recordView, /slimLiveTranscript/);
  assert.match(recordView, /api\.setLiveTranscript/);
  assert.match(recordView, /liveTranscription:[\s\S]*liveTranscriptPreferenceOn/);
});
