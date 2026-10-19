// Wires the keyboard layer into the page: the registry (app-commands.js), the
// dispatcher (keys.js), the user's keymap (localStorage, import, export, reset),
// the held modifiers, the command palette, the cheat sheet, the menu bar and the
// status-bar hints. app.js calls setupKeyboard once.

import { registerAppCommands } from "./app-commands.js";
import { registerCandidateCommands } from "./candidate-commands.js";
import { cheatSheetData, createCheatSheet } from "./cheatsheet.js";
import { commandRecords, searchAll } from "./command-search.js";
import { createCommandSearch, createSearchPanel } from "./command-search-ui.js";
import { synonymsFor } from "./command-synonyms.js";
import { createRegistry } from "./commands.js";
import { registerEditCommands } from "./edit-commands.js";
import { registerExportCommands } from "./export-commands.js";
import { resolveHints } from "./hints.js";
import { ensureCatalog, formatNumber, getLanguage, LANGUAGES, tIn } from "./i18n.js";
import {
  formatCombo,
  loadOverrides,
  parseOverrideText,
  resolveKeymap,
  safeStorage,
  saveOverrides,
  serializeOverrides,
  validateOverrides,
} from "./keymap-config.js";
import { DEFAULT_KEYMAP, STATUS_HINTS } from "./keymap-default.js";
import { createKeymap, detectPlatform } from "./keys.js";
import { registerLoudnessCommands } from "./loudness-commands.js";
import { registerMarkerCommands } from "./marker-commands.js";
import { MENU, MENU_ALIASES, resolveMenu } from "./menu-model.js";
import { createMenubar } from "./menubar.js";
import { createModifierTracker } from "./modifiers.js";
import { createPalette, paletteRows } from "./palette.js";
import { registerPlaceholderCommands } from "./placeholder-commands.js";
import { loadRecent, recordRecent, saveRecent } from "./recent-commands.js";
import { registerSaveCommands } from "./save-commands.js";
import { registerSelectCommands } from "./select-commands.js";
import { subscribe } from "./store.js";
import { registerSyncCommands } from "./sync-commands.js";
import { registerTranscriptCommands } from "./transcript-commands.js";

// Which keymap context a keyboard panel gives (keymap-default.js). The help panel
// is docked in the sidebar, so it takes the side panels' keys: the timeline's
// letters and arrows do not fire while the keyboard is in help.
export const CONTEXT_OF_PANEL = {
  timeline: "timeline",
  transcript: "transcript",
  inspector: "side",
  candidates: "candidates",
  clipboard: "side",
  markers: "markers",
  history: "side",
  help: "side",
};

/**
 * `onRefresh(entries)` is called whenever the keys or the language change (the Help button shows F1 from it).
 * `help` (WP75, Help search): { topics() -> the loaded help topics, load() -> promise of them,
 * open(id) -> show that topic }; read lazily, the help panel is made after this.
 */
export function setupKeyboard({
  actions,
  app,
  t,
  notify,
  onLanguageChange,
  onRefresh,
  prefs,
  help = null,
}) {
  const platform = detectPlatform();
  const storage = safeStorage();
  const registry = createRegistry();
  // Quick actions: the last commands run, from keys or the palette (ids only, per user).
  let recent = prefs ? loadRecent(prefs) : [];
  registry.onRun((id) => {
    const next = recordRecent(recent, id);
    if (next.join() === recent.join()) return;
    recent = next;
    if (prefs) saveRecent(prefs, recent);
  });
  const label = (key) => t(key);
  const format = (raw, forPlatform) => formatCombo(raw, forPlatform);

  // -- the user's keys -------------------------------------------------------------
  let overrides = {};
  let entries = [];
  const problemText = (problem) =>
    problem.code === "not-object"
      ? t("ui.keymap.problem.not-object")
      : t(`ui.keymap.problem.${problem.code}`, {
          id: problem.id,
          combo: problem.combo ?? "",
          with: (problem.with ?? []).join(", "),
        });

  const keymap = createKeymap({
    platform,
    registry,
    getState: app.getState,
    getContext: () => CONTEXT_OF_PANEL[app.getState().panel] ?? "timeline",
  });

  function useOverrides(next, { persist = true } = {}) {
    overrides = next;
    entries = resolveKeymap(DEFAULT_KEYMAP, overrides, platform);
    keymap.setEntries(entries);
    if (persist && !saveOverrides(storage, overrides) && Object.keys(overrides).length > 0) {
      notify(t("ui.keymap.saved_off"), "error");
    }
    refreshAll();
  }

  // -- commands --------------------------------------------------------------------
  const tracker = createModifierTracker({ platform });
  let palette;
  let cheat;
  let menubar;
  let searchPanel;
  registerAppCommands(registry, {
    actions,
    app: {
      ...app,
      openPalette: () => palette.toggle(),
      // Help search (WP75): the field in the in-window Help menu; the panel over the window
      // where there is no such menu (or the desktop app's native Help menu asks for it).
      openSearch: () => (menubar?.openSearch() ? true : searchPanel.open()),
      openKeys: () => cheat.toggle(),
      importKeys: () => importKeys(),
      exportKeys: () => exportKeys(),
      resetKeys: () => {
        useOverrides({});
        notify(t("ui.keymap.reset"), "ok");
      },
    },
  });
  registerEditCommands(registry, {
    app,
    t,
    formatSeconds: (seconds) => formatNumber(seconds, { digits: 1 }),
  });
  registerSelectCommands(registry, { app });
  registerTranscriptCommands(registry, { app, t });
  registerLoudnessCommands(registry, { app, t });
  registerExportCommands(registry, { app, t });
  registerSaveCommands(registry, { app, t });
  registerMarkerCommands(registry, { app, t });
  registerSyncCommands(registry, { app, t });
  registerPlaceholderCommands(registry, { app, t });
  registerCandidateCommands(registry, { app, t });
  // The rest of the sheet is listed everywhere and does nothing until its WP lands.
  registry.planMissing(DEFAULT_KEYMAP.map((entry) => entry.id));

  function importKeys() {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "application/json,.json";
    input.addEventListener("change", async () => {
      const file = input.files?.[0];
      if (!file) return;
      const parsed = parseOverrideText(await file.text());
      if (!parsed.ok) return notify(t("ui.keymap.unreadable"), "error");
      const result = validateOverrides(parsed.value, DEFAULT_KEYMAP, platform);
      useOverrides(result.accepted);
      const count = Object.keys(result.accepted).length;
      if (result.problems.length === 0) notify(t("ui.keymap.imported", { count }), "ok");
      else {
        notify(
          t("ui.keymap.problems", {
            count: result.problems.length,
            details: result.problems.map(problemText).join(" "),
          }),
          "error",
        );
      }
    });
    input.click();
  }

  function exportKeys() {
    const blob = new Blob([serializeOverrides(overrides)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "kuulas-keys.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    notify(t("ui.keymap.exported"), "ok");
  }

  // -- surfaces ----------------------------------------------------------------------
  // The names in the other language(s) also find a command (people remember the English name
  // from other programs); Help search and the palette share this (command-search.js).
  const otherLabels = () =>
    LANGUAGES.filter((lang) => lang !== getLanguage()).map((lang) => (key) => tIn(lang, key));
  for (const lang of LANGUAGES) void ensureCatalog(lang).then(() => refreshSearch());
  const rows = (query) =>
    paletteRows({
      entries,
      registry,
      state: app.getState(),
      query,
      label,
      format,
      platform,
      recent,
      otherLabels: otherLabels(),
      synonymsFor,
    });

  // -- Help search (WP75) --------------------------------------------------------------
  const searchRecords = () =>
    commandRecords({
      entries,
      registry,
      state: app.getState(),
      menu: MENU,
      aliases: MENU_ALIASES,
      label,
      otherLabels: otherLabels(),
      format,
      platform,
      synonymsFor,
      reasons: {
        planned: t("ui.search.reason.planned"),
        noProject: t("ui.search.reason.no_project"),
        unavailable: t("ui.search.reason.unavailable"),
      },
    });
  const makeSearch = (hooks) =>
    createCommandSearch({
      t,
      hooks,
      search: (query) =>
        searchAll({ records: searchRecords(), topics: help?.topics() ?? [], query, recent }),
      run: (id) => registry.run(id, null, app.getState()),
      reveal: (id) => menubar?.reveal(id) ?? false,
      openTopic: (id) => help?.open(id),
    });
  const menuSearch = makeSearch({});
  menuSearch.input.addEventListener(
    "focus",
    () => void help?.load().then(() => menuSearch.refresh()),
  );
  searchPanel = createSearchPanel({
    t,
    makeSearch: (hooks) => makeSearch(hooks),
  });
  function refreshSearch() {
    if (menubar?.isOpen()) menuSearch.refresh();
    searchPanel?.refresh();
  }
  palette = createPalette({
    getRows: rows,
    t,
    run(id) {
      palette.close();
      return registry.run(id, null, app.getState());
    },
  });
  palette.element.querySelector("input").placeholder = t("ui.palette.placeholder");
  const dock = document.querySelector(".editor");
  dock?.append(palette.element);

  cheat = createCheatSheet({
    t,
    getHeld: tracker.held,
    getData: (query) => cheatSheetData({ entries, registry, query, label, format, platform }),
    actions: {
      importKeys: () => importKeys(),
      exportKeys: () => exportKeys(),
      resetKeys: () => registry.run("keymap.reset"),
    },
  });

  const hintBar = document.getElementById("keyhints");
  const menuHint = document.getElementById("menu-hint");
  function renderHints() {
    if (!hintBar) return;
    const state = app.getState();
    const items = resolveHints({
      panel: CONTEXT_OF_PANEL[state.panel] ?? "timeline",
      hints: STATUS_HINTS,
      entries,
      registry,
      state,
      held: tracker.held(),
      label,
      format,
      platform,
    });
    hintBar.replaceChildren(
      ...items.map((item) => {
        const span = document.createElement("span");
        if (item.alternate) span.dataset.alternate = "";
        const kbd = document.createElement("kbd");
        kbd.textContent = item.keys;
        const word = document.createElement("span");
        word.textContent = item.label;
        span.append(kbd, word);
        return span;
      }),
    );
  }

  const root = document.getElementById("menubar");
  if (root) {
    menubar = createMenubar({
      root,
      t,
      search: menuSearch,
      getMenus: () =>
        resolveMenu({
          menu: MENU,
          entries,
          registry,
          state: app.getState(),
          label,
          platform,
          held: tracker.held(),
        }),
      run: (id, arg) => registry.run(id, arg ?? null, app.getState()),
      onHint(text) {
        if (!menuHint || !hintBar) return;
        menuHint.textContent = text ?? "";
        menuHint.hidden = !text;
        hintBar.hidden = Boolean(text);
      },
    });
  }

  function refreshAll() {
    renderHints();
    menubar?.refresh();
    searchPanel?.refresh();
    palette.refresh();
    cheat.refresh();
    onRefresh?.(entries);
  }

  // -- events ------------------------------------------------------------------------
  tracker.subscribe(refreshAll);
  subscribe((_state, patch) => {
    if (
      !patch ||
      "panel" in patch ||
      "project" in patch ||
      "recentProjects" in patch ||
      "canUndo" in patch ||
      "canRedo" in patch
    ) {
      renderHints();
      if (menubar?.isOpen()) menubar.refresh();
    }
  });
  onLanguageChange(() => {
    root?.setAttribute("aria-label", t("menu.bar"));
    palette.element.querySelector("input").placeholder = t("ui.palette.placeholder");
    refreshAll();
  });
  document.addEventListener("keydown", (event) => {
    tracker.update(event);
    if (!event.isComposing) keymap.handle(event);
  });
  document.addEventListener("keyup", (event) => tracker.update(event));
  // A modifier released while the window had no focus never sends a keyup; pointer
  // events carry the truth, and blur or a hidden tab let go of everything.
  document.addEventListener("pointermove", (event) => tracker.update(event), { passive: true });
  window.addEventListener("blur", () => tracker.reset());
  document.addEventListener("visibilitychange", () => document.hidden && tracker.reset());

  // -- start --------------------------------------------------------------------------
  const loaded = validateOverrides(loadOverrides(storage), DEFAULT_KEYMAP, platform);
  useOverrides(loaded.accepted, { persist: false });
  if (loaded.problems.length > 0 && Object.keys(loadOverrides(storage)).length > 0) {
    notify(
      t("ui.keymap.problems", {
        count: loaded.problems.length,
        details: loaded.problems.map(problemText).join(" "),
      }),
      "error",
    );
  }
  return {
    registry,
    keymap,
    palette,
    cheat,
    searchPanel,
    refresh: refreshAll,
    /**
     * Label, keys and tooltip for these command ids, as the menu bar shows them now:
     * a Map id -> { label, keys, tooltip } (the timeline context menus read it).
     */
    describe(ids) {
      const [menu] = resolveMenu({
        menu: [
          {
            id: "ctx",
            labelKey: "ui.context_menu",
            items: ids.map((id) => ({ kind: "item", id })),
          },
        ],
        entries,
        registry,
        state: app.getState(),
        label,
        platform,
        held: tracker.held(),
      });
      return new Map(menu.items.map((item) => [item.baseId, item]));
    },
    /** The keymap the user has right now (defaults with overrides): what help reads. */
    entries: () => entries,
    /** A combo as the user reads it: "⇧⌘Z" or "Ctrl+Shift+Z", the same as the cheat sheet. */
    format: (combo) => format(combo, platform),
  };
}
