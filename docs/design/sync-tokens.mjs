// Copies ui/tokens.css and the pure UI modules into the prototype, between
// their markers, so the prototype stays one offline file and never drifts
// from the app. Run after changing any of them:  node docs/design/sync-tokens.mjs
// ui/tests/tokens.test.js fails until you do.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const at = (path) => fileURLToPath(new URL(path, import.meta.url));
const file = at("prototype/index.html");
let html = readFileSync(file, "utf8");

/** The modules the prototype runs as-is (no imports; exports become plain names). */
export const EMBEDDED = ["grammar.js", "labels.js", "crosstalk.js", "motion.js", "ab-value.js"];

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
for (const name of EMBEDDED) {
  const code = readFileSync(at(`../../ui/${name}`), "utf8").replace(/^export /gm, "").trim();
  replaceBetween(`// -- ${name} (copy) --`, `// -- end of ${name} --`, `// -- ${name} (copy) --\n${code}`);
}
writeFileSync(file, html);
console.log("prototype tokens and modules updated");
