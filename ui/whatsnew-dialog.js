import { enhanceDialog } from "./dialog-keys.js";

// Help > What's New… and the after-upgrade showing: the server's /api/whats-new
// reads the shipped CHANGELOG.md, so the dialog only lays the entries out. The
// changelog's own markdown is plain: "- **Lead.** text" bullets; render exactly
// that (escaped, bold lead) and nothing fancier.

function renderBody(container, markdown) {
  const list = document.createElement("ul");
  list.className = "whatsnew-list";
  for (const line of markdown.split("\n")) {
    const text = line.replace(/^- /, "").trim();
    if (!text) continue;
    const item = document.createElement("li");
    const lead = text.match(/^\*\*(.+?)\*\*\s*(.*)$/);
    if (lead) {
      const strong = document.createElement("strong");
      strong.textContent = lead[1];
      item.append(strong, ` ${lead[2]}`);
    } else {
      item.textContent = text;
    }
    list.append(item);
  }
  container.append(list);
}

/**
 * `api`: { getWhatsNew(after) }; `t` translates; `onShown()` marks the version seen.
 * Returns { element, open(after) }; open() asks the server afresh every time -
 * `after` null shows the current version's notes, a version shows everything since.
 */
export function createWhatsNewDialog({ api, t, onShown }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet whatsnew-dialog";
  dialog.setAttribute("aria-labelledby", "whatsnew-title");

  const heading = document.createElement("h2");
  heading.id = "whatsnew-title";
  const body = document.createElement("div");
  // cheatsheet-body gives the fixed-title / scrolling-body / fixed-footer
  // split the dialog design intends (max-height + overflow on the body).
  body.className = "cheatsheet-body whatsnew-body";
  body.setAttribute("aria-live", "polite");

  const buttons = document.createElement("div");
  buttons.className = "cheatsheet-footer";
  const close = document.createElement("button");
  close.type = "button";
  close.className = "button block primary";
  close.textContent = t("ui.whatsnew.close");
  close.dataset.icon = "close";
  close.dataset.dialogCancel = "";
  close.dataset.dialogPrimary = "";
  close.addEventListener("click", () => dialog.close());
  buttons.append(close);
  dialog.append(heading, body, buttons);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  async function open(after = null) {
    heading.textContent = t("ui.whatsnew.title");
    body.replaceChildren();
    let result;
    try {
      result = await api.getWhatsNew(after);
    } catch {
      return false; // a missing answer is no dialog, never an error
    }
    if (!result?.entries?.length) return false;
    heading.textContent = t("ui.whatsnew.title_in", { version: result.version });
    for (const entry of result.entries) {
      const section = document.createElement("section");
      const sub = document.createElement("h3");
      sub.className = "whatsnew-version";
      sub.textContent = t("ui.whatsnew.version_line", { version: entry.version, date: entry.date });
      section.append(sub);
      renderBody(section, entry.body);
      body.append(section);
    }
    if (!dialog.open) dialog.showModal();
    // The changelog always opens at its top, whatever an earlier opening
    // scrolled to (the rAF pass catches engines that settle scroll late).
    body.scrollTop = 0;
    requestAnimationFrame(() => {
      body.scrollTop = 0;
    });
    onShown?.(result.version);
    return true;
  }

  return { element: dialog, open };
}
