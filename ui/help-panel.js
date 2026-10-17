// The help panel (WP48): docked in the sidebar, never a modal. It shows the
// topic for what the user is looking at (help.js helpChain), with the live
// shortcuts, "Show me" highlights and runnable commands, and a search over all
// topics and commands. The content is data: ui/help/<lang>/<id>.md.
import {
  commandLabelKey,
  createTopicLoader,
  helpChain,
  renderHelpBody,
  searchHelp,
  shortcutsFor,
  topicFor,
  topicForCommand,
} from "./help.js";
import { getLanguage, onLanguageChange, t } from "./i18n.js";

const HIGHLIGHT_MS = 2400;
// The panel's frame; every word in it is set from the catalog by chrome().
const SHELL = `
    <header class="help-head">
      <button type="button" class="button ghost small help-back" hidden></button>
      <h2 class="help-title" tabindex="-1"></h2>
      <span class="spacer"></span>
      <button type="button" class="button ghost icon help-close">×</button>
    </header>
    <input type="search" class="input help-search" />
    <p class="help-about hint"></p>
    <div class="help-body"></div>
    <label class="help-follow hint"><input type="checkbox" checked /> <span></span></label>`;

/**
 * root: the empty <section> in the sidebar. getContext() -> helpChain's context,
 * plus `command` (a command id) when the keyboard is on a menu item: F1 there
 * opens the topic that lists the command, else the index.
 * keymap() -> the keymap entries the user has now (shell-keys.js entries()), the
 * data the cheat sheet and menus read; format(combo) writes a key as they do.
 * commands() -> ids to search and run. runCommand(id) runs one. fetchText(path)
 * reads a help file.
 */
export function createHelpPanel({
  root,
  getContext,
  keymap,
  format,
  commands,
  runCommand,
  fetchText,
}) {
  const doc = root.ownerDocument;
  const loader = createTopicLoader(fetchText);
  let topics = [];
  let topicsLang = null;
  let current = null; // the topic id shown, or null for the index
  let trail = []; // topic ids for Back
  let returnFocus = null;

  root.innerHTML = SHELL;
  const q = (selector) => root.querySelector(selector);
  const body = q(".help-body");
  const search = q(".help-search");

  async function ensureTopics() {
    const lang = getLanguage();
    if (topicsLang === lang) return topics;
    const ids = await loader.index();
    topics = await Promise.all(ids.map((id) => loader.load(id, lang)));
    topicsLang = lang;
    return topics;
  }

  const ctx = () => ({
    t,
    shortcuts: (command) => shortcutsFor(command, keymap()),
    format,
    title: (id) => topics.find((topic) => topic.id === id)?.title ?? id,
  });

  function chrome() {
    q(".help-back").textContent = `← ${t("ui.help.back")}`;
    q(".help-back").hidden = trail.length === 0;
    q(".help-close").setAttribute("aria-label", t("ui.help.close"));
    q(".help-close").title = `${t("ui.help.close")} (${t("key.escape")})`;
    search.placeholder = t("ui.help.search");
    search.setAttribute("aria-label", t("ui.help.search"));
    q(".help-follow span").textContent = t("ui.help.follow");
    root.setAttribute("aria-label", t("ui.help.title"));
  }

  function showTopic(topic) {
    current = topic.id;
    q(".help-title").textContent = topic.title;
    q(".help-about").textContent = topic.fallback ? t("ui.help.fallback") : "";
    body.innerHTML = renderHelpBody(topic.body, ctx());
    chrome();
  }

  function showIndex(query = "") {
    current = null;
    q(".help-title").textContent = t("ui.help.index");
    q(".help-about").textContent = "";
    const found = searchHelp(
      topics.map((topic) => ({ ...topic, text: topic.body })),
      query,
    );
    const cmds = query.trim()
      ? searchHelp(
          commands().map((id) => ({
            id,
            title: t(commandLabelKey(id)),
            // The id's words too: "zoom" finds Lähennä in Finnish.
            text: `${t(`cmd.${id}.hint`)} ${id.replace(/[._]/g, " ")}`,
          })),
          query,
        )
      : [];
    const list = (items) => `<ul class="help-results">${items.join("")}</ul>`;
    let html = "";
    if (found.length)
      html += `<h3>${t("ui.help.topics")}</h3>${list(found.map((topic) => `<li><a href="#help:${topic.id}" class="help-link" data-topic="${topic.id}"></a></li>`))}`;
    if (cmds.length)
      html += `<h3>${t("ui.help.commands")}</h3>${list(cmds.map((c) => `<li class="help-command"><button type="button" class="button small help-run" data-run="${c.id}"></button><span class="keys"></span><span class="hint"></span></li>`))}`;
    if (!found.length && !cmds.length) html = `<p class="hint help-empty"></p>`;
    body.innerHTML = html;
    // Text goes in as text: titles and hints are data, never markup.
    for (const a of body.querySelectorAll("a[data-topic]"))
      a.textContent = ctx().title(a.dataset.topic);
    for (const li of body.querySelectorAll(".help-command")) {
      const id = li.querySelector("[data-run]").dataset.run;
      li.querySelector("[data-run]").textContent = t(commandLabelKey(id));
      li.querySelector(".hint").textContent = t(`cmd.${id}.hint`);
      const keys = shortcutsFor(id, keymap());
      li.querySelector(".keys").innerHTML = keys.map(() => "<kbd></kbd>").join(" ");
      li.querySelectorAll("kbd").forEach((kbd, i) => {
        kbd.textContent = format(keys[i]);
      });
    }
    const empty = body.querySelector(".help-empty");
    if (empty) empty.textContent = t("ui.help.no_results", { query });
    chrome();
  }

  async function goTo(id, { push = true } = {}) {
    await ensureTopics();
    const topic = topics.find((x) => x.id === id);
    if (!topic) return showIndex();
    if (push && current && current !== id) trail.push(current);
    showTopic(topic);
  }

  /** Point at a control for a moment. A control that is hidden at rest is named instead. */
  function showMe(id) {
    const target = doc.querySelector(`[data-help-id="${id}"]`);
    if (!target) return;
    target.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    target.classList.remove("help-highlight");
    void target.offsetWidth; // restart the animation when pressed twice
    target.classList.add("help-highlight");
    setTimeout(() => target.classList.remove("help-highlight"), HIGHLIGHT_MS);
  }

  root.addEventListener("click", (event) => {
    const link = event.target.closest("[data-topic]");
    if (link) {
      event.preventDefault();
      void goTo(link.dataset.topic);
      return;
    }
    const show = event.target.closest("[data-show]");
    if (show) return showMe(show.dataset.show);
    const run = event.target.closest("[data-run]");
    if (run) return runCommand(run.dataset.run);
    if (event.target.closest(".help-back")) {
      const back = trail.pop();
      if (back) void goTo(back, { push: false });
      else showIndex(search.value);
    }
    if (event.target.closest(".help-close")) close();
  });
  search.addEventListener("input", () => {
    if (current) trail.push(current);
    showIndex(search.value);
  });
  root.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      close();
    }
  });
  onLanguageChange(() => {
    if (root.hidden) return;
    topicsLang = null;
    void (current ? goTo(current, { push: false }) : ensureTopics().then(() => showIndex()));
  });

  async function open() {
    const inside = root.contains(doc.activeElement);
    if (!inside) returnFocus = doc.activeElement;
    root.hidden = false;
    root.closest(".sidebar")?.toggleAttribute("data-help-open", true);
    await ensureTopics();
    // F1 again inside help: the index and search.
    if (inside) {
      showIndex(search.value);
      search.focus();
      return;
    }
    trail = [];
    const context = getContext();
    // On a menu item: its command's topic, else the index (not the panel behind the menu).
    if (context.command) {
      const own = topicForCommand(context.command, topics);
      if (own) showTopic(own);
      else showIndex();
      q(".help-title").focus();
      return;
    }
    const topic = topicFor(helpChain(context), topics);
    if (topic) showTopic(topic);
    else showIndex();
    q(".help-title").focus();
  }

  function close() {
    root.hidden = true;
    root.closest(".sidebar")?.toggleAttribute("data-help-open", false);
    if (returnFocus?.isConnected) returnFocus.focus();
    returnFocus = null;
  }

  /** Called on state changes: with "Follow" on, the topic follows the selection. */
  function update() {
    if (root.hidden || !q(".help-follow input").checked || !topics.length) return;
    // While the keyboard is in help, help is what has focus: keep the topic.
    if (root.contains(doc.activeElement)) return;
    const topic = topicFor(helpChain(getContext()), topics);
    if (topic && topic.id !== current) showTopic(topic);
  }

  return { open, close, update, showMe, isOpen: () => !root.hidden };
}
