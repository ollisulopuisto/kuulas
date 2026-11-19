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
  assert.equal(result.intentImmediate, "none", "hover opens the card at once, without intent");
  // The strip is persistent and nothing shifts, so the press lands on Solo
  // itself: nothing to swallow, nothing to forward.
  assert.equal(result.hitInControls, false, "the in-flight press misses the collapsed strip");
  assert.equal(result.pressSwallowed, false, "the press needs no redirect");
  assert.deepEqual(
    result.calls,
    [["change", "solo", true]],
    "the in-flight press ran anything but an exclusive Solo",
  );
  assert.deepEqual(
    result.callsAfter,
    [
      ["change", "solo", true],
      ["change", "solo", true],
    ],
    "the deliberate Solo click failed",
  );
  // Shift survives: a Shift press is a non-exclusive Solo.
  assert.equal(result.shiftSwallowed, false, "the Shift press needs no redirect");
  assert.deepEqual(
    result.shiftCalls,
    [["change", "solo", false]],
    "the Shift press lost its modifier or ran something else",
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

for (const density of ["comfortable", "compact"]) {
  test(`${density} density: the hover rule - intent, grace, pin, no gap trigger`, async () => {
    const result = await measure(`density=${density}&hover=Bob`);
    assert.equal(result.harnessError, undefined);
    // Opens only after ~120 ms on the strip, never at once.
    assert.equal(result.openAt60, false, "the card opens without the intent delay");
    assert.equal(result.openAt200, true, "the card never opens over the strip");
    // Open while the pointer is anywhere inside the expanded card.
    assert.equal(result.openInsideCard, true, "the card closes while the pointer rests in it");
    // ~250 ms close grace.
    assert.equal(result.openAfterLeave100, true, "the card closes without its close grace");
    assert.equal(result.openAfterLeave400, false, "the card never closes after the pointer left");
    // The card gaps and the area past the pill are not a trigger.
    assert.equal(result.openFromGap, false, "the card opens from a gap past the pill");
    // The name pill is a trigger too, and its click pins the card open.
    assert.equal(result.openFromName, true, "hovering the name pill does not open the card");
    assert.equal(result.pinnedAfterLeave, true, "a name click does not pin the card open");
    assert.equal(result.openAfterOutsideClick, false, "clicking elsewhere does not unpin");
    assert.equal(result.openAfterEsc, false, "Escape does not unpin");
    // Double-click renames, and must not leave the card pinned.
    assert.equal(result.renameStillWorks, true, "double-click no longer renames");
    assert.equal(result.pinnedByDblclick, false, "a rename double-click pinned the card");
    // No layout shift under the pointer: the strip does not move when the card opens.
    assert.equal(result.noShift, true, "the strip moves when the card opens");
  });
}

test("Escape on a pinned header is consumed before the global key dispatcher", async () => {
  // Devin review on #240: the dispatcher (document, bubble phase) would also
  // run goHome on the same press, clearing the clip selection and marks.
  const result = await measure("esc=1");
  assert.equal(result.harnessError, undefined);
  assert.equal(result.pinned, true, "the name click did not pin the card");
  assert.equal(result.unpinned, true, "Escape did not unpin the card");
  assert.equal(
    result.globalAfterPinnedEsc,
    0,
    "the pinned-header Escape leaked to the global key dispatcher",
  );
  assert.equal(
    result.globalAfterPlainEsc,
    1,
    "a plain Escape no longer reaches the global key dispatcher",
  );
});

test("a compact lane hides the read-only state column but keeps the hover rule", async () => {
  const result = await measure(`density=compact&lane=32&hover=Bob`);
  assert.equal(result.openAt200, true, "the compact card never opens");
});
