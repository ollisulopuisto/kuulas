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
  const url = `http://127.0.0.1:${port}/tests/browser/menu-shortcut.html?${query}`;
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

test("Finnish long label keeps shortcut on the first line in a shared right column", async () => {
  const rows = await measure("");
  assert.equal(rows.length, 2);
  for (const row of rows) {
    assert.ok(Math.abs(row.keyTop - row.firstTop) < 5, JSON.stringify(row));
    assert.ok(row.rowRight <= 800, JSON.stringify(row));
  }
  assert.ok(Math.abs(rows[0].keyRight - rows[1].keyRight) < 1);
});
