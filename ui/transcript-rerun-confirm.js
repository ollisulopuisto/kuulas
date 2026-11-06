import { enhanceDialog } from "./dialog-keys.js";

export function createTranscriptRerunConfirm({ t }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet sync-confirm";
  dialog.setAttribute("aria-labelledby", "transcript-rerun-title");
  const heading = document.createElement("h2");
  heading.id = "transcript-rerun-title";
  const message = document.createElement("p");
  const footer = document.createElement("div");
  footer.className = "cheatsheet-footer";
  const button = (label, extra, value) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `button block ${extra}`.trim();
    item.textContent = label;
    item.addEventListener("click", () => dialog.close(value));
    return item;
  };
  const cancel = button(t("ui.transcript.rerun_cancel"), "", "cancel");
  const confirm = button(t("ui.transcript.rerun_confirm"), "primary", "confirm");
  cancel.dataset.icon = "close";
  confirm.dataset.icon = "check";
  cancel.dataset.dialogCancel = "";
  confirm.dataset.dialogPrimary = "";
  footer.append(cancel, confirm);
  dialog.append(heading, message, footer);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  return {
    ask(name) {
      heading.textContent = t("ui.transcript.rerun_confirm_title");
      message.textContent = t("ui.transcript.rerun_confirm_body", { name });
      return new Promise((resolve) => {
        dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), {
          once: true,
        });
        dialog.returnValue = "cancel";
        dialog.showModal();
        cancel.focus();
      });
    },
  };
}
