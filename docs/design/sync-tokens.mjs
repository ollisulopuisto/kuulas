// Copies ui/tokens.css into the prototype, between its two token markers, so
// the prototype stays a single offline file and never drifts from the app.
// Run after any change to ui/tokens.css:  node docs/design/sync-tokens.mjs
// ui/tests/tokens.test.js fails until you do.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const at = (path) => fileURLToPath(new URL(path, import.meta.url));
const tokens = readFileSync(at("../../ui/tokens.css"), "utf8").trim();
const file = at("prototype/index.html");
const html = readFileSync(file, "utf8");
const START = "/* kuulas design tokens.";
const END = "/* -- end of tokens.css -- */";
const from = html.indexOf(START);
const to = html.indexOf(END);
if (from < 0 || to < from) throw new Error("token markers not found in the prototype");
writeFileSync(file, `${html.slice(0, from)}${tokens}\n${html.slice(to)}`);
console.log("prototype tokens updated");
