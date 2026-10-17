// Copies ui/tokens.css and ui/grammar.js into the prototype, between their
// markers, so the prototype stays one offline file and never drifts from the
// app. Run after changing either file:  node docs/design/sync-tokens.mjs
// ui/tests/tokens.test.js fails until you do.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const at = (path) => fileURLToPath(new URL(path, import.meta.url));
const file = at("prototype/index.html");
let html = readFileSync(file, "utf8");

function replaceBetween(start, end, content) {
  const from = html.indexOf(start);
  const to = html.indexOf(end);
  if (from < 0 || to < from) throw new Error(`markers not found: ${start}`);
  html = `${html.slice(0, from)}${content}\n${html.slice(to)}`;
}

replaceBetween(
  "/* kuulas design tokens.",
  "/* -- end of tokens.css -- */",
  readFileSync(at("../../ui/tokens.css"), "utf8").trim(),
);
// The prototype is a classic script: the module's exports become plain names.
const grammar = readFileSync(at("../../ui/grammar.js"), "utf8").replace(/^export /gm, "").trim();
replaceBetween("// -- grammar.js (copy) --", "// -- end of grammar.js --", `// -- grammar.js (copy) --\n${grammar}`);
writeFileSync(file, html);
console.log("prototype tokens and grammar updated");
