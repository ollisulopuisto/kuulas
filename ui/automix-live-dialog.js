import {
  LIVE_MAX_LINES,
  LIVE_POLL_MS,
  liveStatusKey,
  mergeLive,
  shouldPoll,
  stickToBottom,
} from "./automix-live-model.js";
import { enhanceDialog } from "./dialog-keys.js";
// "Automixer log" (File > Show automixer log…, and the running toast's Show log): everything the
// automixer has printed so far, live. It asks GET /api/automix/live once a second while it is
// open and the run goes on; closed, it asks nothing. The pure parts are automix-live-model.js.

/**
 * `api`: { automixLive }; `t` translates; `copyText(text)` copies. Returns { element, open() }.
 */
export function createAutomixLiveDialog({ api, t, copyText }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet automix-live-dialog";
  dialog.setAttribute("aria-labelledby", "automix-live-title");

  const heading = document.createElement("h2");
  heading.id = "automix-live-title";
  heading.textContent = t("ui.automix.live_title");
  const status = document.createElement("p");
  status.className = "form-note";
  status.setAttribute("role", "status");
  // A focusable, selectable, scrollable block; one text node, appended to as lines arrive.
  const text = document.createElement("pre");
  text.className = "automix-live-text";
  text.tabIndex = 0;
  text.setAttribute("aria-label", t("ui.automix.live_title"));
  let node = document.createTextNode("");
  text.append(node);

  const buttons = document.createElement("div");
  buttons.className = "cheatsheet-footer";
  const button = (labelKey, onClick, extra = "") => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `button block ${extra}`.trim();
    b.textContent = t(labelKey);
    b.addEventListener("click", onClick);
    return b;
  };
  let lines = [];
  let started = null;
  const copy = button("ui.automix.live_copy", () => void copyText(lines.join("\n")));
  const close = button("ui.stats.close", () => dialog.close(), "primary");
  close.dataset.icon = "close";
  close.dataset.dialogCancel = "";
  close.dataset.dialogPrimary = "";
  copy.classList.add("footer-start");
  buttons.append(copy, close);
  dialog.append(heading, status, text, buttons);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  let timer = null;
  let running = false;
  // Bumped on every open and close: an answer that arrives after that is dropped.
  let round = 0;

  function show(view) {
    const follow = stickToBottom(text);
    const { reset, add } = mergeLive({ lines, started }, view);
    started = view.started;
    if (reset) {
      lines = add.slice();
      node.data = lines.join("\n");
    } else if (add.length) {
      const joined = lines.length ? `\n${add.join("\n")}` : add.join("\n");
      lines.push(...add);
      if (lines.length > LIVE_MAX_LINES) {
        lines = lines.slice(-LIVE_MAX_LINES);
        node.data = lines.join("\n"); // trimmed: the one time the text is replaced
      } else {
        node.appendData(joined);
      }
    }
    running = view.running;
    status.textContent = t(liveStatusKey(running));
    if (reset || follow) text.scrollTop = text.scrollHeight;
  }

  async function poll(mine) {
    try {
      const view = await api.automixLive();
      if (mine !== round) return;
      show(view);
    } catch (error) {
      if (mine !== round) return;
      status.textContent = error.message;
      return;
    }
    if (shouldPoll({ open: dialog.open, running })) {
      timer = setTimeout(() => void poll(mine), LIVE_POLL_MS);
    }
  }

  function stop() {
    round += 1;
    clearTimeout(timer);
    timer = null;
  }
  dialog.addEventListener("close", stop);

  return {
    element: dialog,
    async open() {
      stop();
      lines = [];
      started = null;
      node = document.createTextNode("");
      text.replaceChildren(node);
      running = false;
      status.textContent = t("ui.automix.live_loading");
      if (!dialog.open) dialog.showModal();
      text.focus();
      await poll(round);
    },
  };
}
