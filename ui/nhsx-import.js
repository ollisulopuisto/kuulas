// File > Import Hindenburg session… : the checks before the server is asked and the sentence
// said afterwards. The import itself is the server command `import_nhsx` (Session.import_nhsx):
// it adds the session's tracks, regions, words and clipboard to the open project in one undo
// step, and links the recordings in place.
import { isAbsolutePath } from "./project-name.js";

/** { ok: true, body: { path } } or { ok: false, key } for a path that cannot be a .nhsx file. */
export function nhsxRequest(typed) {
  let path = typeof typed === "string" ? typed.trim() : "";
  // A path copied from a file manager often comes in quotes.
  if (/^(["']).*\1$/.test(path)) path = path.slice(1, -1).trim();
  if (path === "") return { ok: false, key: "ui.nhsx.need_path" };
  if (!isAbsolutePath(path)) return { ok: false, key: "ui.nhsx.need_path" };
  if (!path.toLowerCase().endsWith(".nhsx")) return { ok: false, key: "ui.nhsx.need_nhsx" };
  return { ok: true, body: { path } };
}

/** What to say after the import: `summary` is summariseImport(report) of the server's answer. */
export function nhsxResult(summary) {
  const count = summary.imported;
  const missing = summary.failures.length;
  if (count === 0) return { key: "ui.nhsx.nothing", values: { missing }, kind: "error" };
  if (missing > 0) return { key: "ui.nhsx.partial", values: { count, missing }, kind: "warn" };
  return { key: "ui.nhsx.done", values: { count }, kind: "ok" };
}
