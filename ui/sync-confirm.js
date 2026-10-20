// Sync asks first (owner, 2026-10-19: "sync or restore sync is almost a spiritual brother to
// undo ... it should ask, and even say what it is going to do first"). The server's preview
// (POST /api/sync/preview) lists what a moving sync command would do; this file words it and shows
// it in a small dialog with Confirm (Enter) and Cancel (Esc). Free / unsync moves nothing and
// never asks. The wording and the list are pure (describeMoves); the dialog is thin DOM.

/** Clips named in the dialog before "and N more". */
export const SHOWN = 4;

/** "+1.24 s" / "−0.31 s": `frames` at `rate`; `format(number)` writes the magnitude (2 decimals). */
export function formatShift(frames, rate, format) {
  const sign = frames < 0 ? "−" : "+";
  return `${sign}${format(Math.abs(frames) / rate)} s`;
}

/**
 * The words for a preview: `{ title, lines, more }`. `t` translates; `format(number)` writes a
 * number in the UI language with two decimals (the shift in seconds).
 */
export function describeMoves(preview, { t, format }) {
  const home = preview.command === "send_home";
  const label = (move) => (move.name ? `${move.track} · ${move.name}` : move.track);
  const lines = preview.moves.slice(0, SHOWN).map((move) =>
    home
      ? t("ui.sync.confirm.line_home", { clip: label(move), track: move.to_track ?? move.track })
      : t("ui.sync.confirm.line", {
          clip: label(move),
          shift: formatShift(move.shift, preview.rate, format),
        }),
  );
  const rest = preview.moves.length - lines.length;
  const title = home
    ? t("ui.sync.confirm.title_home", { count: preview.count })
    : t("ui.sync.confirm.title", { count: preview.count, anchor: preview.anchor });
  return { title, lines, more: rest > 0 ? t("ui.sync.confirm.more", { count: rest }) : "" };
}

/**
 * The dialog. `ask(preview)` resolves true on Confirm (button or Enter) and false on Cancel or Esc.
 * Built once, reused.
 */
export function createSyncConfirm({ t, format }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet sync-confirm";
  dialog.setAttribute("aria-labelledby", "sync-confirm-title");
  const heading = document.createElement("h2");
  heading.id = "sync-confirm-title";
  const list = document.createElement("ul");
  list.className = "sync-confirm-list";
  const more = document.createElement("p");
  const footer = document.createElement("div");
  footer.className = "cheatsheet-footer";
  const button = (label, extra, onClick) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `button block ${extra}`.trim();
    b.textContent = label;
    b.addEventListener("click", onClick);
    return b;
  };
  const cancel = button(t("ui.sync.confirm.cancel"), "", () => dialog.close("cancel"));
  const confirm = button(t("ui.sync.confirm.confirm"), "primary", () => dialog.close("confirm"));
  cancel.dataset.icon = "close";
  confirm.dataset.icon = "check";
  footer.append(cancel, confirm);
  dialog.append(heading, list, more, footer);
  document.body.append(dialog);
  // Enter confirms from anywhere in the dialog (a focused Cancel keeps its own Enter).
  dialog.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target !== cancel) {
      event.preventDefault();
      dialog.close("confirm");
    }
  });

  return {
    element: dialog,
    ask(preview) {
      const d = describeMoves(preview, { t, format });
      heading.textContent = d.title;
      list.replaceChildren(
        ...d.lines.map((text) => {
          const li = document.createElement("li");
          li.textContent = text;
          return li;
        }),
      );
      more.textContent = d.more;
      more.hidden = d.more === "";
      return new Promise((resolve) => {
        dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), {
          once: true,
        });
        dialog.returnValue = "cancel";
        dialog.showModal();
        confirm.focus();
      });
    },
  };
}
