// Layout and pointer regressions for the compact track headers, run in a real browser: the
// real tracks.js and style.css in tests/browser/headers.html. Needs Chrome or Chromium (set
// CHROME to point at one); without it the suite fails, never skips (docs/PLAN.md, no skipped tests).
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
  for (const rail of ["icons", "labels"]) {
    test(`${density} density, ${rail} rail: grouped and ungrouped names keep a column`, async () => {
      const { names, bus } = await measure(`density=${density}&rail=${rail}`);
      const grouped = Object.values(names).filter((item) => item.grouped);
      const plain = Object.values(names).filter((item) => !item.grouped);
      assert.equal(grouped.length, 2);
      assert.equal(plain.length, 2);
      for (const item of [...grouped, ...plain]) {
        assert.equal(item.header.width, 120);
        assert.ok(item.width >= MIN_NAME_PX, `name column ${item.width}px`);
      }
      assert.ok(bus.name.width >= MIN_NAME_PX, `bus name ${bus.name.width}px`);
    });
  }
  test(`${density} density: a bus header is one column wide and its summary stays inside it`, async () => {
    const { bus } = await measure(`density=${density}`);
    assert.equal(bus.columns.split(" ").length, 1);
    assert.ok(bus.summary.left >= bus.header.left - 0.5);
    assert.ok(bus.summary.left + bus.summary.width <= bus.header.left + bus.header.width + 0.5);
    assert.ok(bus.controls.width >= 100, `bus controls ${bus.controls.width}px`);
  });
  test(`${density} density: double-clicking a grouped and an ungrouped name renames it`, async () => {
    for (const open of ["Bob", "Last"]) {
      const result = await measure(`density=${density}&open=${open}`);
      assert.equal(result.nameHit, "track-name");
      assert.equal(result.renameField, true);
    }
  });
}

for (const lane of [80, 140, 240]) {
  test(`${lane}px lane: the open flyout leaves the resize grip and the next header alone`, async () => {
    const result = await measure(`density=comfortable&lane=${lane}&open=Bob`);
    assert.ok(result.flyout, "the flyout opens on hover");
    assert.equal(result.gripHit, true, "the grip is what a pointer hits at its centre");
    assert.equal(overlap(result.flyout, result.grip), false);
    assert.equal(overlap(result.flyout, result.next), false);
    assert.deepEqual(result.calls, [["setLaneHeight", "t2", null]], "double-click resets the lane");
  });
}
