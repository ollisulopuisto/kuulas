// Layout and pointer regressions for the overlay track headers (header redesign,
// 2026-11-18), run in a real browser: the real tracks.js and style.css in
// tests/browser/headers.html. Needs Chrome or Chromium (set CHROME to point at one);
// without it the suite fails, never skips (docs/PLAN.md, no skipped tests).
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
const MIN_NAME_PX = 28;

let server;
let port;
before(async () => {
  server = createServer((req, res) => {
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

async function measure(query) {
  assert.ok(chrome, "no Chrome found: install Chrome/Chromium or set CHROME to its path");
  const url = `http://127.0.0.1:${port}/tests/browser/headers.html?${query}`;
  const { stdout: dom } = await run(
    chrome,
    [
      "--headless",
      "--no-sandbox",
      "--disable-gpu",
      "--window-size=800,700",
      "--virtual-time-budget=4000",
      "--dump-dom",
      url,
    ],
    { encoding: "utf8", timeout: 30000 },
  );
  const text = dom.match(/<pre id="result">([\s\S]*?)<\/pre>/)[1];
  return JSON.parse(text.replaceAll("&quot;", '"').replaceAll("&amp;", "&"));
}

test("Chrome or Chromium is installed for the browser regressions", () => {
  assert.ok(chrome, "no Chrome found: install Chrome/Chromium or set CHROME to its path");
});
const overlap = (a, b) =>
  a.left < b.left + b.width &&
  b.left < a.left + a.width &&
  a.top < b.top + b.height &&
  b.top < a.top + a.height;

for (const density of ["comfortable", "compact"]) {
  test(`${density} density: names show whole in pills over transparent lanes`, async () => {
    const { names, bus } = await measure(`density=${density}`);
    const grouped = Object.values(names).filter((item) => item.grouped);
    const plain = Object.values(names).filter((item) => !item.grouped);
    assert.equal(grouped.length, 2);
    assert.equal(plain.length, 2);
    for (const item of [...grouped, ...plain]) {
      // Full names, never an ellipsis (his standing call).
      assert.ok(item.untruncated, `name truncated at ${item.width}px`);
      assert.ok(item.width >= MIN_NAME_PX, `name pill ${item.width}px`);
      // The lane shows through around the card; the strip is the drag handle.
      assert.ok(item.headerTransparent, "the header row hides the waveform");
      assert.ok(item.strip.width >= 24 && item.strip.width <= 36, `strip ${item.strip.width}px`);
    }
    assert.ok(bus.name.width >= MIN_NAME_PX, `bus name ${bus.name.width}px`);
    // Bus members sit further right than ungrouped tracks.
    assert.ok(grouped[0].left > plain[0].left, "grouped names are not indented");
  });
  test(`${density} density: a bus header is a card with its badge in the strip`, async () => {
    const { bus } = await measure(`density=${density}`);
    assert.ok(bus.badge, "bus badge is not in the strip");
    // Collapsed, only the strip and the name pill show.
    assert.equal(bus.controlsDisplay, "none");
    assert.equal(bus.summaryDisplay, "none");
  });
  test(`${density} density: double-clicking a grouped and an ungrouped name renames it`, async () => {
    for (const open of ["Bob", "Last"]) {
      const result = await measure(`density=${density}&open=${open}`);
      assert.equal(result.nameHit, "track-name");
      assert.equal(result.renameField, true);
    }
  });
}

test("a fast press at Solo's original centre runs only Solo (Devin, #233)", async () => {
  const result = await measure(`density=comfortable&intent=Bob`);
  assert.equal(result.intentImmediate, "flex", "hover does not open the card at once");
  assert.equal(
    result.hitInControls,
    true,
    "the in-flight press no longer lands on the revealed controls",
  );
  assert.equal(result.pressSwallowed, true, "the in-flight press is not swallowed");
  assert.deepEqual(result.calls, [["change", "solo"]], "the in-flight press ran anything but Solo");
  assert.deepEqual(
    result.callsAfter,
    [
      ["change", "solo"],
      ["change", "solo"],
    ],
    "the deliberate Solo click failed",
  );
  assert.equal(result.intentAfter, "flex", "the card closes while the pointer rests");
});

test("the card's pan dial never reveals the stray fixed readout (Devin, #233)", async () => {
  const result = await measure(`density=comfortable&pan=Bob`);
  assert.equal(result.panOutputDisplay, "none", "the pan readout shows in the card");
});

for (const lane of [80, 140, 240]) {
  test(`${lane}px lane: the pinned popover leaves the resize grip alone`, async () => {
    const result = await measure(`density=comfortable&lane=${lane}&open=Bob`);
    assert.ok(result.flyout, "the popover opens from the disclosure");
    assert.equal(result.controlsOpen, true, "pinning keeps the card expanded");
    assert.equal(result.gripHit, true, "the grip is what a pointer hits at its centre");
    assert.equal(overlap(result.flyout, result.grip), false);
    assert.deepEqual(result.calls, [["setLaneHeight", "t2", null]], "double-click resets the lane");
  });
}
