// Real-browser regression (owner, 2026-11-19): long imported speaker names
// must not leave block rows in a character-wide strip beside the legend.
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

test("speaker names do not squeeze block rows into a single-character column", async () => {
  assert.ok(chrome, "Chrome required");
  const { stdout } = await run(chrome, [
    "--headless",
    "--no-sandbox",
    "--disable-gpu",
    "--window-size=1140,800",
    "--virtual-time-budget=2000",
    "--dump-dom",
    `http://127.0.0.1:${port}/tests/browser/block-level-width.html`,
  ]);
  const widths = JSON.parse(stdout.match(/<pre id="result">([\s\S]*?)<\/pre>/)[1]);
  assert.equal(widths.length, 12);
  for (const width of widths) assert.ok(width > 140, `block text collapsed to ${width}px`);
});
