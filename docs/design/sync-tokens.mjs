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
export const EMBEDDED = [
  "grammar.js",
  "labels.js",
  "crosstalk.js",
  "motion.js",
  "ab-value.js",
  "help.js",
];

/** The help topics as one object, { "en/clip": text, ... }: the prototype renders the real files. */
export function helpFiles() {
  const index = JSON.parse(readFileSync(at("../../ui/help/index.json"), "utf8")).topics;
  const files = {};
  for (const lang of ["en", "fi"])
    for (const id of index) files[`${lang}/${id}`] = readFileSync(at(`../../ui/help/${lang}/${id}.md`), "utf8");
  // The help panel's words and the command labels and hints, for the prototype's t().
  for (const lang of ["en", "fi"]) {
    const catalog = JSON.parse(readFileSync(at(`../../src/kuulas/locales/${lang}.json`), "utf8"));
    files[`catalog/${lang}`] = Object.fromEntries(
      Object.entries(catalog).filter(([key]) => /^(cmd|ui\.help)\./.test(key)),
    );
  }
  return files;
}

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
replaceBetween(
  "// -- help topics (copy) --",
  "// -- end of help topics --",
  `// -- help topics (copy) --\nconst HELP_FILES = ${JSON.stringify(helpFiles(), null, 1)};`,
);
writeFileSync(file, html);
console.log("prototype tokens and modules updated");
