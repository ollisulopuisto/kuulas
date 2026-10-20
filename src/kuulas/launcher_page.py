"""The desktop start page: Open / New and the recent projects (HTML as one string).

The page is loaded with ``load_html``, so it cannot import files: it carries the
design tokens, the shared ``.button`` rules, the icon set and the row model
(``ui/launcher-model.js``, tested with node) inline, plus the recents as JSON that
the page script turns into rows. Every string comes through ``t``; the relative
times ("2 min ago") are the browser's ``Intl.RelativeTimeFormat`` in the page
language. Nothing here opens a project or reads one.
"""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

from .messages import t
from .paths import find_ui_dir
from .recent_projects import normalize_record

ICON_DIR = Path(__file__).parent / "assets" / "icons"

#: The part of ``ui/style.css`` that styles ``.button`` (between these two marks).
_BUTTONS_FROM = "/* -- buttons and chips"
_BUTTONS_TO = ".chip {"

_PAGE_CSS = """
html{background:var(--surface-lane)}
body{margin:0;background:var(--surface-lane);color:var(--text);
 font:var(--text-md)/var(--leading-body) var(--font-ui)}
main{max-width:44rem;margin:0 auto;padding:var(--space-8) var(--space-6)}
h1{display:flex;align-items:center;gap:var(--space-5);margin:0 0 var(--space-6);
 font-size:var(--text-xl);font-weight:var(--weight-strong)}
.mark{border-radius:22%}
h2{margin:var(--space-7) 0 var(--space-4);font-size:var(--text-sm);
 font-weight:var(--weight-strong);color:var(--text-secondary);
 text-transform:uppercase;letter-spacing:.04em}
.actions{display:flex;gap:var(--space-4);flex-wrap:wrap}
.button{font:inherit;font-size:var(--text-sm)}
#recent-list{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-3)}
.row{position:relative;display:block;width:100%;box-sizing:border-box;text-align:left;font:inherit;
 color:var(--text);cursor:pointer;padding:var(--space-4) var(--space-5);
 background:var(--surface-raised);border:1px solid var(--border-subtle);
 border-radius:var(--radius-md);
 transition:background var(--dur-fast) var(--ease-standard),
  border-color var(--dur-fast) var(--ease-standard)}
.row:hover{background:var(--surface-hover);border-color:var(--border)}
.row:active{background:var(--surface-active)}
.row .name{display:block;font-size:var(--text-lg);font-weight:var(--weight-strong);
 line-height:var(--leading-tight);overflow-wrap:anywhere}
.row .path{display:block;margin-top:var(--space-1);font-size:var(--text-xs);
 color:var(--text-tertiary);overflow-wrap:anywhere}
.row .meta{display:flex;flex-wrap:wrap;gap:var(--space-2) var(--space-5);
 margin-top:var(--space-3);font-size:var(--text-sm)}
.row .meta span.fact{white-space:nowrap}
.row .meta .k{color:var(--text-tertiary)}
.row .meta .v{color:var(--text-secondary);font-variant-numeric:tabular-nums}
.row .meta .v[title]{cursor:help;text-decoration:underline dotted;
 text-underline-offset:3px}
.row .note{display:block;margin-top:var(--space-3);font-size:var(--text-sm);
 color:var(--warn-text)}
.row.missing{cursor:not-allowed;background:transparent;border-style:dashed}
.row.missing .name,.row.missing .path,.row.missing .meta{opacity:.6}
.row.missing:hover{background:transparent;border-color:var(--border-subtle)}
.row.keyed{padding-right:calc(var(--space-5) + 4.5rem)}
.keychip{position:absolute;right:var(--space-5);top:50%;transform:translateY(-50%);
 min-width:18px;height:18px;padding:0 var(--space-2);box-sizing:border-box;
 font:var(--weight-medium) var(--text-xs)/16px var(--font-ui);
 font-variant-numeric:tabular-nums;text-align:center;white-space:nowrap;
 color:var(--kbd-text);background:var(--kbd-bg);border:1px solid var(--kbd-border);
 border-bottom-width:2px;border-radius:var(--radius-xs)}
.empty{color:var(--text-secondary);margin:0}
"""


def _css() -> str:
    ui = find_ui_dir(__file__)
    tokens = (ui / "tokens.css").read_text(encoding="utf-8")
    style = (ui / "style.css").read_text(encoding="utf-8")
    start = style.find(_BUTTONS_FROM)
    end = style.find(_BUTTONS_TO, start)
    buttons = style[start:end] if 0 <= start < end else ""
    focus = ":focus-visible{outline:var(--focus-width) solid var(--focus-ring);" \
            "outline-offset:var(--focus-offset)}"
    return "\n".join((tokens, buttons, focus, _PAGE_CSS))


def _modules() -> str:
    ui = find_ui_dir(__file__)
    return "\n".join((ui / name).read_text(encoding="utf-8")
                     for name in ("icons.js", "launcher-model.js"))


def _json_for_script(data: object) -> str:
    """JSON that cannot end its ``<script>`` element or start a comment in it."""
    return (json.dumps(data, ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


_MAIN = """
installIcons(document);
const data = JSON.parse(document.getElementById("recent-data").textContent);
const api = () => window.pywebview?.api;
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};
const wire = (id, icon, method) => {
  const button = document.getElementById(id);
  button.dataset.icon = icon;
  button.addEventListener("click", () => api()?.[method]());
};
wire("open", "import", "choose_project");
wire("new", "follow", "new_project");

const list = document.getElementById("recent-list");
const now = Date.now();
const hostOs = navigator.userAgentData?.platform ?? navigator.platform ?? "";
const platform = /mac/i.test(hostOs) ? "mac" : "other";
const chips = rowKeyChips(data.rows.length, platform);
// One way in for the click and the key, so a missing folder behaves the same and a second
// press while the window is switching cannot open the project twice.
let opening = false;
const openRow = (model) => {
  if (model.missing || opening) return;
  opening = true;
  setTimeout(() => {
    opening = false;
  }, 1000);
  api()?.open_project(model.path);
};
const models = [];
for (const [at, record] of data.rows.entries()) {
  const model = rowModel(record, now, data.lang, data.labels);
  const row = el("button", model.missing ? "row missing" : "row");
  row.type = "button";
  row.tabIndex = -1;
  row.title = model.note ?? model.path;
  row.append(el("span", "name", model.name), el("span", "path", model.path));
  if (model.chips.length > 0) {
    const meta = el("span", "meta");
    for (const chip of model.chips) {
      const fact = el("span", "fact");
      const value = el("span", "v", chip.text);
      if (chip.title) value.title = chip.title;
      fact.append(el("span", "k", `${chip.label} `), value);
      meta.append(fact);
    }
    row.append(meta);
  }
  if (model.missing) {
    row.setAttribute("aria-disabled", "true");
    row.append(el("span", "note", model.note));
  }
  models.push(model);
  if (chips[at]) {
    const chip = el("kbd", "keychip", chips[at]);
    row.classList.add("keyed");
    const modKey = platform === "mac" ? "Meta" : "Control";
    row.setAttribute("aria-keyshortcuts", `${modKey}+${at + 1}`);
    row.append(chip);
  }
  row.addEventListener("click", () => openRow(model));
  const item = document.createElement("li");
  item.append(row);
  list.append(item);
}
document.addEventListener("keydown", (event) => {
  const at = rowForKey(event, platform, models.length);
  if (at === null) return;
  event.preventDefault();
  openRow(models[at]);
});
const rows = [...list.querySelectorAll(".row")];
if (rows.length > 0) rows[0].tabIndex = 0;
list.addEventListener("keydown", (event) => {
  const next = nextRow(rows.indexOf(document.activeElement), event.key, rows.length);
  if (next === null) return;
  event.preventDefault();
  for (const row of rows) row.tabIndex = -1;
  rows[next].tabIndex = 0;
  rows[next].focus();
});
list.addEventListener("focusin", (event) => {
  const at = rows.indexOf(event.target);
  if (at < 0) return;
  for (const row of rows) row.tabIndex = -1;
  rows[at].tabIndex = 0;
});
"""


def launcher_html(recent: list) -> str:
    """The start page for ``recent``: records (``path``, ``exists``, ``opened_utc``,
    ``tracks``, ``duration_s``, ``size_bytes``; all but ``path`` optional) or bare
    path strings. A record without metadata shows only its name, path and, if
    known, when it was opened."""
    rows = []
    for item in recent:
        record = normalize_record(item)
        if record is None:
            continue
        rows.append({**record, "exists": item.get("exists", True)
                     if isinstance(item, dict) else True})
    lang = t("desktop.launcher.lang")
    data = {
        "lang": lang,
        "labels": {key: t(f"desktop.launcher.{key}")
                   for key in ("opened", "tracks", "duration", "size", "size_tip",
                               "missing")},
        "rows": rows,
    }
    none = html.escape(t("desktop.launcher.none"))
    empty = "" if rows else f'<p class="empty">{none}</p>'
    new = html.escape(t("desktop.launcher.new"))
    open_ = html.escape(t("desktop.launcher.open"))
    recent_heading = html.escape(t("desktop.launcher.recent"))
    mark = base64.b64encode((ICON_DIR / "kuulas-icon.svg").read_bytes()).decode()
    return f"""<!doctype html><html lang="{html.escape(lang)}">
<head><meta charset="utf-8"><title>kuulas</title>
<meta name="color-scheme" content="light dark">
<style>
{_css()}
</style></head><body><main>
<h1><img class="mark" alt="" width="40" height="40"
src="data:image/svg+xml;base64,{mark}"> kuulas</h1>
<div class="actions">
<button type="button" class="button primary" id="open">{open_}</button>
<button type="button" class="button" id="new">{new}</button>
</div>
<h2 id="recent-heading">{recent_heading}</h2>{empty}
<ul id="recent-list" aria-labelledby="recent-heading"></ul>
</main>
<script type="application/json" id="recent-data">{_json_for_script(data)}</script>
<script type="module">
{_modules()}
{_MAIN}
</script></body></html>"""
