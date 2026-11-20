// Approved overview A (owner, 2026-11-19): filters, explicit gain meaning,
// selected-block actions and stale-result safety in a real browser.
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const run = promisify(execFile);
const ui = fileURLToPath(new URL("..", import.meta.url));
const chrome = [
  process.env.CHROME,
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].find((path) => path && existsSync(path));
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" };

let server;
let port;
before(async () => {
  server = createServer((req, res) => {
    if (req.url.startsWith("/api/locales/")) {
      const lang = req.url.endsWith("/fi") ? "fi" : "en";
      res.writeHead(200, { "content-type": "application/json" });
      res.end(readFileSync(join(ui, `../src/kuulas/locales/${lang}.json`)));
      return;
    }
    const path = normalize(join(ui, new URL(req.url, "http://x").pathname));
    if (!path.startsWith(ui) || !existsSync(path)) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { "content-type": types[extname(path)] ?? "application/octet-stream" });
    res.end(readFileSync(path));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  port = server.address().port;
});
after(() => server.close());

test("overview keeps selection, filters and stale apply safe", async () => {
  assert.ok(chrome, "Chrome required");
  const { stdout } = await run(chrome, [
    "--headless",
    "--no-sandbox",
    "--disable-gpu",
    "--window-size=1000,1000",
    "--virtual-time-budget=2000",
    "--dump-dom",
    `http://127.0.0.1:${port}/tests/browser/block-overview.html`,
  ]);
  const result = JSON.parse(
    stdout.match(/<pre id="result">([\s\S]*?)<\/pre>/)[1].replaceAll("&amp;", "&"),
  );
  assert.equal(result.speakerTabs, 3);
  assert.equal(result.sharedToggleColors, true);
  assert.equal(result.oneSpeaker, 1);
  assert.equal(result.ownZero, true);
  assert.match(result.estimate, /Arvio/);
  assert.match(result.countedApply, /15/);
  assert.match(result.switchedSpeaker, /guest232006/);
  assert.equal(result.hiddenPrevious, true);
  assert.equal(result.bars, 15);
  assert.equal(result.closedList, true);
  assert.match(result.legend, /Nosto.*Vaimennus/);
  assert.equal(result.help, true);
  assert.match(result.detail, /Vaimennus −8,0 dB/);
  assert.deepEqual(result.listened, ["0:1"]);
  assert.deepEqual(result.jumped, ["0:1"]);
  assert.equal(result.excluded, true);
  assert.match(result.afterExclusion, /8,0/);
  assert.match(result.footerAfterExclusion, /14/);
  assert.match(result.leftAfterExclusion, /4/);
  assert.equal(result.liftDisabled, true);
  assert.equal(result.manualExclusionKept, true);
  assert.equal(result.enabledInRange, 6);
  assert.equal(result.staleApplyDisabled, true);
  assert.equal(result.closedAfterApply, true);
  assert.deepEqual(result.applied.skip, []);
});

test("filtered apply sends every unselected block as skip", async () => {
  const { stdout } = await run(chrome, [
    "--headless",
    "--no-sandbox",
    "--disable-gpu",
    "--window-size=1000,1000",
    "--virtual-time-budget=2000",
    "--dump-dom",
    `http://127.0.0.1:${port}/tests/browser/block-overview.html?filtered=1`,
  ]);
  const result = JSON.parse(
    stdout.match(/<pre id="result">([\s\S]*?)<\/pre>/)[1].replaceAll("&amp;", "&"),
  );
  const all = result.applied.measured.speakers
    .flatMap((s) => s.blocks)
    .filter((r) => r.gain_db !== 0)
    .map((r) => r.id);
  const kept = all.filter((id) => !result.applied.skip.includes(id));
  assert.deepEqual(kept, ["0:2", "1:1", "1:2", "2:1", "2:2"]);
});

test("a speaker without changes gets the no-change card and a link to the others", async () => {
  const { stdout } = await run(chrome, [
    "--headless",
    "--no-sandbox",
    "--disable-gpu",
    "--window-size=1000,1000",
    "--virtual-time-budget=2000",
    "--dump-dom",
    `http://127.0.0.1:${port}/tests/browser/block-overview.html?nochange=a`,
  ]);
  const result = JSON.parse(
    stdout.match(/<pre id="result">([\s\S]*?)<\/pre>/)[1].replaceAll("&amp;", "&"),
  );
  assert.equal(result.cardVisible, true);
  assert.equal(result.cardTitle, "Ei muutoksia: Olli");
  assert.match(result.cardSpan, /^Taso pysyy välillä /);
  assert.equal(result.beforeHidden, true);
  assert.equal(result.afterHidden, true);
  assert.equal(result.countHidden, true);
  assert.equal(result.leftHidden, false);
  assert.equal(result.graphHidden, true);
  assert.equal(result.legendHidden, false);
  assert.equal(result.footer, "Kaikki puhujat: 1 lohko (2026-11-19-t03-04-25pm-guest232006--panu)");
  assert.equal(result.applyText, "Tasaa 1 lohko");
  assert.equal(result.applyDisabled, false);
  assert.equal(result.applyPrimary, true);
  assert.equal(result.againPrimary, false);
  assert.equal(result.primaryLast, true);
  assert.equal(result.otherLink, "2026-11-19-t03-04-25pm-guest232006--panu · 1 lohko muuttuu →");
  assert.match(result.linkActivated, /guest232006/);
  assert.equal(result.linkTargetCardHidden, true);
  assert.match(result.linkTargetCount, /1 lohkoa muuttuu/);
});

test("nothing to level anywhere: one statement, disabled apply, primary re-measure", async () => {
  const { stdout } = await run(chrome, [
    "--headless",
    "--no-sandbox",
    "--disable-gpu",
    "--window-size=1000,1000",
    "--virtual-time-budget=2000",
    "--dump-dom",
    `http://127.0.0.1:${port}/tests/browser/block-overview.html?nochange=b`,
  ]);
  const result = JSON.parse(
    stdout.match(/<pre id="result">([\s\S]*?)<\/pre>/)[1].replaceAll("&amp;", "&"),
  );
  assert.equal(result.cardVisible, true);
  assert.equal(result.cardTitle, "✓ Ei tasattavaa");
  assert.match(result.cardSpan, /^Kaikki 24 lohkoa ovat jo vaihteluvälillä /);
  assert.equal(result.beforeHidden, true);
  assert.equal(result.countHidden, true);
  assert.equal(result.leftHidden, true);
  assert.equal(result.graphHidden, true);
  assert.equal(result.legendHidden, true);
  assert.equal(result.footer, "Kaikki puhujat: 0 lohkoa");
  assert.equal(result.applyText, "Ei tasattavaa");
  assert.equal(result.applyDisabled, true);
  assert.equal(result.applyPrimary, false);
  assert.equal(result.againPrimary, true);
  assert.equal(result.primaryLast, true);
  assert.equal(result.otherLink, null);
});
