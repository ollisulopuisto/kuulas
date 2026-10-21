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
#recent-list li{position:relative}
.row-actions{position:absolute;top:50%;right:var(--space-5);transform:translateY(-50%);
 display:flex;gap:var(--space-2);opacity:0;pointer-events:none}
li.keyed .row-actions{right:calc(var(--space-5) + 4.5rem)}
li:hover .row-actions,li:focus-within .row-actions{opacity:1;pointer-events:auto}
.row-actions .button{font-size:var(--text-xs);padding:var(--space-1) var(--space-3);
 background:var(--surface-raised)}
.row.pulse{outline:2px solid var(--focus-ring);outline-offset:1px;
 background:var(--surface-hover);border-color:var(--focus-ring)}
@media (prefers-reduced-motion:no-preference){
 .row.pulse{animation:pulse 180ms var(--ease-standard)}
}
@keyframes pulse{
 0%{transform:scale(1);filter:brightness(1)}
 50%{transform:scale(1.015);filter:brightness(1.12)}
 100%{transform:scale(1);filter:brightness(1)}
}
.tidy{margin-top:var(--space-5)}
[hidden]{display:none!important}
#toast{position:fixed;left:50%;bottom:var(--space-6);transform:translateX(-50%);
 display:flex;align-items:center;gap:var(--space-4);max-width:36rem;
 padding:var(--space-4) var(--space-5);background:var(--surface-raised);color:var(--text);
 border:1px solid var(--border);border-radius:var(--radius-md);
 box-shadow:var(--shadow-raised);font-size:var(--text-sm)}
#toast[hidden]{display:none}
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
const hostOs = navigator.userAgentData?.platform ?? navigator.platform ?? "";
const platform = /mac/i.test(hostOs) ? "mac" : "other";
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const L = data.labels;
let entries = data.rows;
let models = [];
let rowEls = [];
let focusAt = 0;

// A small message with optional buttons; one at a time. "Removed X" has Undo, "Remove the
// missing ones?" has Confirm / Cancel. Nothing here touches a project folder.
const toastEl = document.getElementById("toast");
let toastTimer = 0;
const toast = (text, buttons = [], ms = 8000) => {
  clearTimeout(toastTimer);
  toastEl.replaceChildren(el("span", "", text));
  for (const { label, run } of buttons) {
    const button = el("button", "button", label);
    button.type = "button";
    button.addEventListener("click", () => {
      toastEl.hidden = true;
      run();
    });
    toastEl.append(button);
  }
  toastEl.hidden = false;
  if (ms > 0) toastTimer = setTimeout(() => (toastEl.hidden = true), ms);
};

const opener = createOpener({
  reducedMotion,
  schedule: (fn, ms) => setTimeout(fn, ms),
  highlight: (at) => rowEls[at]?.classList.add("pulse"),
  unhighlight: (at) => rowEls[at]?.classList.remove("pulse"),
  open: (model) => api()?.open_project(model.path),
  explain: (model) => toast(L.missing_open.replace("{name}", model.name), [], 10000),
});

const removeAt = (path) => {
  const { rows, removed, index } = removeEntry(entries, path);
  if (!removed) return;
  entries = rows;
  render();
  void api()?.remove_recent(path);
  toast(
    L.removed.replace("{name}", folderName(path)),
    [
      {
        label: L.undo,
        run: () => {
          entries = restoreEntry(entries, removed, index);
          render();
          void api()?.restore_recent(removed, index);
        },
      },
    ],
    10000,
  );
};

const tidy = document.getElementById("tidy");
tidy.addEventListener("click", () => {
  const gone = missingPaths(entries);
  if (gone.length === 0) return;
  toast(
    L.tidy_confirm,
    [
      {
        label: L.tidy,
        run: () => {
          entries = entries.filter((row) => row.exists !== false);
          render();
          void api()?.remove_missing_recents();
        },
      },
      { label: L.cancel, run: () => {} },
    ],
    0,
  );
});

function actionButton(kind, model) {
  const button = el("button", "button", L[kind]);
  button.type = "button";
  button.tabIndex = -1;
  button.title = L[`${kind}_tip`];
  button.dataset.action = kind;
  button.addEventListener("click", () => {
    if (kind === "remove") removeAt(model.path);
    else void api()?.locate_recent(model.path);
  });
  return button;
}

function render() {
  const now = Date.now();
  const chips = rowKeyChips(entries.length, platform);
  list.replaceChildren();
  models = [];
  rowEls = [];
  for (const [at, record] of entries.entries()) {
    const model = rowModel(record, now, data.lang, L);
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
    const item = document.createElement("li");
    if (chips[at]) {
      row.classList.add("keyed");
      item.classList.add("keyed");
      const modKey = platform === "mac" ? "Meta" : "Control";
      row.setAttribute("aria-keyshortcuts", `${modKey}+${at + 1}`);
      row.append(el("kbd", "keychip", chips[at]));
    }
    row.addEventListener("click", () => opener.request(model, at, "click"));
    const actions = el("span", "row-actions");
    for (const kind of rowActions(model)) actions.append(actionButton(kind, model));
    item.append(row, actions);
    list.append(item);
    models.push(model);
    rowEls.push(row);
  }
  focusAt = Math.min(focusAt, Math.max(0, rowEls.length - 1));
  if (rowEls.length > 0) rowEls[focusAt].tabIndex = 0;
  document.getElementById("none").hidden = entries.length > 0;
  tidy.hidden = missingPaths(entries).length === 0;
}
render();

document.addEventListener("keydown", (event) => {
  const at = rowForKey(event, platform, models.length);
  if (at === null) return;
  event.preventDefault();
  opener.request(models[at], at, "key");
});
const focusRow = (next) => {
  for (const row of rowEls) row.tabIndex = -1;
  focusAt = next;
  rowEls[next].tabIndex = 0;
  rowEls[next].focus();
};
list.addEventListener("keydown", (event) => {
  const at = rowEls.indexOf(document.activeElement);
  if (at >= 0 && (event.key === "Delete" || event.key === "Backspace")) {
    event.preventDefault();
    removeAt(models[at].path);
    if (rowEls.length > 0) focusRow(Math.min(at, rowEls.length - 1));
    return;
  }
  // Right arrow moves into the row's buttons, Left back to the row.
  const own = rowEls[at]?.parentElement;
  const buttons = [...(own?.querySelectorAll(".row-actions button") ?? [])];
  if (at >= 0 && event.key === "ArrowRight" && buttons.length > 0) {
    event.preventDefault();
    buttons[0].focus();
    return;
  }
  const inActions = document.activeElement?.closest(".row-actions");
  if (inActions) {
    const row = inActions.parentElement.querySelector(".row");
    const group = [...inActions.querySelectorAll("button")];
    const here = group.indexOf(document.activeElement);
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      if (here > 0) group[here - 1].focus();
      else row.focus();
    } else if (event.key === "ArrowRight" && here < group.length - 1) {
      event.preventDefault();
      group[here + 1].focus();
    }
    return;
  }
  const next = nextRow(at, event.key, rowEls.length);
  if (next === null) return;
  event.preventDefault();
  focusRow(next);
});
list.addEventListener("focusin", (event) => {
  const at = rowEls.indexOf(event.target);
  if (at < 0) return;
  for (const row of rowEls) row.tabIndex = -1;
  focusAt = at;
  rowEls[at].tabIndex = 0;
});
// Right click on a row: show its buttons (they are also shown on hover and focus).
list.addEventListener("contextmenu", (event) => {
  const item = event.target.closest("li");
  if (!item) return;
  event.preventDefault();
  item.querySelector(".row-actions button")?.focus();
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
                               "missing", "missing_open", "remove", "remove_tip",
                               "locate", "locate_tip", "removed", "undo", "cancel")}
        | {"tidy": t("cmd.app.remove_missing_recents"),
           "tidy_confirm": t("ui.project.remove_missing_confirm")},
        "rows": rows,
    }
    none = html.escape(t("desktop.launcher.none"))
    empty = f'<p class="empty" id="none"{"" if not rows else " hidden"}>{none}</p>'
    tidy = html.escape(t("cmd.app.remove_missing_recents"))
    tidy_tip = html.escape(t("cmd.app.remove_missing_recents.hint"))
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
<button type="button" class="button tidy" id="tidy" title="{tidy_tip}"
hidden>{tidy}</button>
</main>
<div id="toast" role="status" hidden></div>
<script type="application/json" id="recent-data">{_json_for_script(data)}</script>
<script type="module">
{_modules()}
{_MAIN}
</script></body></html>"""
