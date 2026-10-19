// Transcribe on Colab (WP78): the two small dialogs. The model is colab-model.js; the job is
// followed in the notice area by app.js.
//  - askConsent(names): "The audio is uploaded to Google", with Cancel and "Do not ask again".
//  - openSettings(): the command kuulas runs, its folder, extra arguments, model, language.

import { colabForm, colabSettingsBody } from "./colab-model.js";

const make = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

/**
 * `api`: { colabSettings, saveColabSettings }; `t` translates; `onSettingsSaved()` says so.
 * Returns { askConsent(names) -> Promise<{ ok, remember }>, openSettings() }.
 */
export function createColabDialogs({ api, t, onSettingsSaved = () => {} }) {
  // -- the upload notice ------------------------------------------------------------------------
  const consent = make("dialog", "cheatsheet automix-dialog");
  consent.setAttribute("aria-labelledby", "colab-consent-title");
  const consentTitle = make("h2", "", t("ui.colab.consent_title"));
  consentTitle.id = "colab-consent-title";
  const consentText = make("p", "automix-note");
  const remember = make("input");
  remember.type = "checkbox";
  const rememberLabel = make("label", "automix-field");
  rememberLabel.append(remember, make("span", "", t("ui.colab.consent_remember")));
  const consentForm = make("form");
  consentForm.method = "dialog";
  const consentButtons = make("div", "cheatsheet-footer");
  const consentCancel = make("button", "button", t("ui.colab.consent_cancel"));
  consentCancel.type = "button";
  consentCancel.dataset.icon = "close";
  const consentOk = make("button", "button primary", t("ui.colab.consent_ok"));
  consentOk.type = "submit";
  consentOk.dataset.icon = "check";
  consentButtons.append(consentCancel, consentOk);
  consentForm.append(rememberLabel, consentButtons);
  consent.append(consentTitle, consentText, consentForm);
  document.body.append(consent);

  let settle = null;
  const finish = (ok) => {
    const done = settle;
    settle = null;
    const result = { ok, remember: ok && remember.checked };
    if (consent.open) consent.close();
    done?.(result);
  };
  consentCancel.addEventListener("click", () => finish(false));
  consent.addEventListener("cancel", (event) => {
    event.preventDefault(); // Esc is Cancel, and nothing is uploaded
    finish(false);
  });
  consentForm.addEventListener("submit", (event) => {
    event.preventDefault();
    finish(true);
  });

  // -- the settings -----------------------------------------------------------------------------
  const dialog = make("dialog", "cheatsheet automix-dialog");
  dialog.setAttribute("aria-labelledby", "colab-settings-title");
  const title = make("h2", "", t("ui.colab.settings_title"));
  title.id = "colab-settings-title";
  const error = make("p", "automix-error");
  error.setAttribute("role", "alert");
  error.hidden = true;
  const fields = {};
  const field = (name, labelKey, hintKey) => {
    const label = make("label", "automix-field");
    const input = make("input");
    input.type = "text";
    input.name = name;
    if (hintKey) input.title = t(hintKey);
    label.append(make("span", "", t(labelKey)), input);
    fields[name] = input;
    return label;
  };
  const noDrive = make("input");
  noDrive.type = "checkbox";
  const noDriveLabel = make("label", "automix-field");
  noDriveLabel.append(noDrive, make("span", "", t("ui.colab.no_drive")));
  const align = make("input");
  align.type = "checkbox";
  const alignLabel = make("label", "automix-field");
  alignLabel.append(align, make("span", "", t("ui.colab.align")));
  const form = make("form");
  form.method = "dialog";
  const buttons = make("div", "cheatsheet-footer");
  const close = make("button", "button", t("ui.colab.close"));
  close.type = "button";
  close.dataset.icon = "close";
  close.addEventListener("click", () => dialog.close());
  const save = make("button", "button primary", t("ui.colab.save"));
  save.type = "submit";
  save.dataset.icon = "save";
  buttons.append(close, save);
  form.append(
    field("command", "ui.colab.command", "ui.colab.command_hint"),
    field("cwd", "ui.colab.cwd", "ui.colab.cwd_hint"),
    field("extra", "ui.colab.extra_args"),
    field("model", "ui.colab.model"),
    field("language", "ui.colab.language"),
    alignLabel,
    noDriveLabel,
    error,
    buttons,
  );
  dialog.append(title, form);
  document.body.append(dialog);

  const showError = (message) => {
    error.textContent = message;
    error.hidden = false;
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const values = Object.fromEntries(Object.entries(fields).map(([k, input]) => [k, input.value]));
    try {
      await api.saveColabSettings(
        colabSettingsBody({ ...values, noDrive: noDrive.checked, align: align.checked }),
      );
      dialog.close();
      onSettingsSaved();
    } catch (e) {
      showError(e.message);
    }
  });

  return {
    /** Ask before audio leaves the computer. Resolves { ok, remember }; Esc and Cancel are not ok. */
    askConsent(names) {
      if (settle) return Promise.resolve({ ok: false, remember: false });
      consentText.textContent = t("ui.colab.consent_text", { names });
      remember.checked = false;
      return new Promise((resolve) => {
        settle = resolve;
        consent.showModal();
        consentOk.focus();
      });
    },
    async openSettings() {
      error.hidden = true;
      try {
        const { resolved } = await api.colabSettings();
        const form = colabForm(resolved);
        for (const key of Object.keys(fields)) fields[key].value = form[key];
        noDrive.checked = form.noDrive;
        align.checked = form.align;
      } catch (e) {
        showError(e.message);
      }
      if (!dialog.open) dialog.showModal();
      fields.command.focus();
    },
  };
}
