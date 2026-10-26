// The toolbar's buttons as data (WP86): the layout turned into { id, label, tip, enabled, icon }.
// Pure: the registry, the state, the translator and the key lookup are passed in. The order is
// the layout's and nothing else's; a command that cannot run is only `enabled: false`.

/**
 * The icon of each default command (icons.js), or null: a null is drawn as text so a button is
 * never empty. Transcribe, Auto-Silence, resync and automix borrow the nearest icon that exists
 * (a pencil, the padlock of a closed stretch, a reset arrow, stacked layers); the real icons are
 * still to be chosen (docs/design/TOOLBAR.md, open questions).
 */
export const TOOLBAR_ICONS = Object.freeze({
  "edit.undo": "undo",
  "edit.redo": "redo",
  "app.import": "import",
  "app.transcribe": "rename",
  "app.auto_silence": "lock",
  "edit.split": "cut",
  "clip.mute": "mute",
  "sync.resync_range": "reset",
  "export.automix": "layers",
  "app.export": "export",
});

/**
 * The short label of each default button (message keys): the rail is narrow, and the full command
 * names ("Transcribe the track on this computer") do not fit it. The tip keeps the full name.
 * A command the user pins that is not listed shows its full name.
 */
export const SHORT_LABELS = Object.freeze(
  Object.fromEntries(Object.keys(TOOLBAR_ICONS).map((id) => [id, `ui.rail.short.${id}`])),
);

/** `layout`: command ids; `registry`: { has, can }; `t`: translate; `keyOf(id)`: the key text or "". */
export function toolbarItems({ layout, registry, state, t, keyOf }) {
  return layout.map((id) => {
    const full = t(`cmd.${id}`);
    const key = keyOf(id);
    return {
      id,
      label: id in SHORT_LABELS ? t(SHORT_LABELS[id]) : full,
      tip: key ? `${full} (${key})` : full,
      enabled: registry.has(id) && registry.can(id, state),
      icon: TOOLBAR_ICONS[id] ?? null,
    };
  });
}
