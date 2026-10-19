// File > New project… / Open project… in a plain browser (WP74): the page asks for a name and a
// folder, checks them here, and the server makes the project and opens it in a new tab. The rules
// are the server's (src/kuulas/new_project.py has the last word; tests/test_new_project.py):
// the name becomes a folder name, so it is not empty, at most 100 characters, has no / \ or NUL,
// does not start with a dot, and gets the `.kuulas` suffix once.

const SUFFIX = ".kuulas";
const MAX_NAME = 100;

/** { ok: true, folder } with the suffix added once, or { ok: false, key } for a bad name. */
export function folderName(typed) {
  let text = typeof typed === "string" ? typed.trim() : "";
  if (text.toLowerCase().endsWith(SUFFIX)) text = text.slice(0, -SUFFIX.length).trimEnd();
  const bad = text === "" || text.length > MAX_NAME || text.startsWith(".") || /[/\\\0]/.test(text);
  return bad ? { ok: false, key: "ui.project.bad_name" } : { ok: true, folder: text + SUFFIX };
}

/** Unix (/…), drive (C:\… or C:/…) or UNC (\\…) path, with no `..` part; never ~ or relative. */
export function isAbsolutePath(path) {
  if (typeof path !== "string" || path === "") return false;
  const absolute = path.startsWith("/") || /^[A-Za-z]:[\\/]/.test(path) || path.startsWith("\\\\");
  return absolute && !path.split(/[\\/]/).includes("..");
}

/** The body for POST /api/project/new, or { ok: false, field, key }. */
export function newProjectRequest({ parent, name }) {
  const folder = folderName(name);
  if (!folder.ok) return { ok: false, field: "name", key: folder.key };
  const where = String(parent ?? "").trim();
  if (!isAbsolutePath(where)) return { ok: false, field: "parent", key: "ui.project.need_folder" };
  return { ok: true, body: { parent: where, name: String(name).trim() } };
}

/** The body for POST /api/project/open, or { ok: false, field, key }. */
export function openProjectRequest(path) {
  const where = String(path ?? "").trim();
  if (!isAbsolutePath(where)) return { ok: false, field: "path", key: "ui.project.need_folder" };
  return { ok: true, body: { path: where } };
}
