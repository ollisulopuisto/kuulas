// Clip > Locate / Relink media… (owner, 2026-10-21). The user edited a recording elsewhere
// (say, removed noise) and saved it, maybe under another name: its SHA-256 differs, so File >
// Locate media (which matches by content) cannot take it. Here one picks the file for the
// clip; the server imports it (linked in place: neither file is written or deleted) and
// reports both lengths (session.check_replace_media); the user confirms, warned when the
// lengths differ; one edit, replace_clip_media, points every clip of that recording at the new
// file: one undo step. The same file found elsewhere is a plain relink, nothing to confirm.

import { enhanceDialog } from "./dialog-keys.js";

/**
 * What to show for the server's check. `seconds(frames)` formats a length. Returns
 * { confirm: false, notice } for the same file, else { confirm: true, warn, title, lines, edit }.
 */
export function relinkPlan(report, { t, seconds, mediaId = null }) {
  if (report.same_file) return { confirm: false, notice: t("ui.relink.same_file") };
  const lines = [
    t("ui.relink.replace", { name: report.name, clips: report.clips }),
    t("ui.relink.keeps_original"),
  ];
  const warn = !report.same_length;
  if (warn)
    lines.unshift(
      t("ui.relink.length_differs", {
        old: seconds(report.old_frames),
        new: seconds(report.new_frames),
      }),
    );
  return {
    confirm: true,
    warn,
    title: t("ui.relink.title"),
    lines,
    edit: {
      op: "replace_clip_media",
      args: { media_id: mediaId, new_media_id: report.new_media_id },
    },
  };
}

/** The confirmation dialog. `ask(plan)` resolves true on Replace (button or Enter). */
export function createRelinkConfirm({ t }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet sync-confirm";
  dialog.setAttribute("aria-labelledby", "relink-title");
  const heading = document.createElement("h2");
  heading.id = "relink-title";
  const list = document.createElement("ul");
  list.className = "sync-confirm-list";
  const footer = document.createElement("div");
  footer.className = "cheatsheet-footer";
  const button = (label, extra, value) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `button block ${extra}`.trim();
    b.textContent = label;
    b.addEventListener("click", () => dialog.close(value));
    return b;
  };
  const cancel = button(t("ui.relink.cancel"), "", "cancel");
  const confirm = button(t("ui.relink.confirm"), "primary", "confirm");
  cancel.dataset.icon = "close";
  confirm.dataset.icon = "check";
  cancel.dataset.dialogCancel = "";
  confirm.dataset.dialogPrimary = "";
  footer.append(cancel, confirm);
  dialog.append(heading, list, footer);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });
  return {
    ask(plan) {
      heading.textContent = plan.title;
      list.replaceChildren(
        ...plan.lines.map((text, index) => {
          const li = document.createElement("li");
          li.textContent = text;
          if (plan.warn && index === 0) li.setAttribute("role", "alert");
          return li;
        }),
      );
      return new Promise((resolve) => {
        dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), {
          once: true,
        });
        dialog.returnValue = "cancel";
        dialog.showModal();
        // A length warning puts the focus on Cancel: Enter must not replace by accident.
        (plan.warn ? cancel : confirm).focus();
      });
    },
  };
}
